from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters,
    ConversationHandler
)
import logging
from pymongo import MongoClient
from datetime import datetime
import random
from bson import ObjectId

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# ========== CONFIG ==========


client = MongoClient(MONGO_URI)
db = client.quizdb

quiz_questions_collection = db.quiz_questions
practice_questions_collection = db.questions
scores_collection = db.scores

admin_usernames = ['AmHBbe', 'yeabayras', 'Am21HB6']
admin_ids = [1152440268, 7209995991]

# Conversation states
(
    QUIZ_Q_TEXT, QUIZ_OPT_A, QUIZ_OPT_B, QUIZ_OPT_C, QUIZ_OPT_D, QUIZ_CORRECT,
    PRAC_Q_TEXT, PRAC_OPT_A, PRAC_OPT_B, PRAC_OPT_C, PRAC_OPT_D, PRAC_CORRECT
) = range(12)

# In-memory caches
quiz_questions = []
practice_questions = []

def load_quiz_questions():
    global quiz_questions
    quiz_questions.clear()
    for q in quiz_questions_collection.find():
        q.pop('_id', None)
        quiz_questions.append(q)

def load_practice_questions():
    global practice_questions
    practice_questions.clear()
    for q in practice_questions_collection.find():
        q.pop('_id', None)
        practice_questions.append(q)

def load_all_questions():
    load_quiz_questions()
    load_practice_questions()

# ========== START & MODE SELECTION (improved UX) ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []

    if quiz_questions:
        keyboard.append([InlineKeyboardButton("ፈተና ጀምር 🧠", callback_data='start_quiz')])

    # Prioritize Practice when no quiz is active
    practice_btn = InlineKeyboardButton("መለማመድ ጀምር 📚", callback_data='start_practice')
    if not quiz_questions:
        keyboard.insert(0, [practice_btn])
    else:
        keyboard.append([practice_btn])

    if not keyboard:
        await update.message.reply_text(
            "እንኳን ወደ ቅድስት አርሴማ የመጽሐፍ ቅዱስ ጥናት እራስን መፈተሻ bot በሰላም መጡ! 🙏\n\n"
            "ገና ጥያቄ የለም። አስተዳዳሪ እንዲጨምር ይጠይቁ።"
        )
        return

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = "እንኳን ወደ ቅድስት አርሴማ የመጽሐፍ ቅዱስ ጥናት እራስን መፈተሻ bot በሰላም መጡ! 🙏\n\nየመማሪያ ሞድ ይምረጡ:"
    
    if not quiz_questions:
        text += "\n\n(አሁን ንቁ ፈተና የለም 😔 – መለማመድ ጀምር!)"

    await update.message.reply_text(text, reply_markup=reply_markup)

# ========== QUIZ MODE ==========
async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    if not quiz_questions:
        await (query.message if query else update.message).reply_text(
            "አሁን ንቁ ፈተና የለም 😔\n"
            "መለማመድ (Practice) በመጠቀም ማወቅዎን ይቀጥሉ! 📚\n"
            "/start በመጫን ይሞክሩ"
        )
        return

    user = update.effective_user
    context.user_data.clear()

    context.user_data["mode"] = "quiz"
    context.user_data["score"] = 0
    context.user_data["q_index"] = 0
    context.user_data["user_id"] = user.id
    context.user_data["username"] = user.username or str(user.id)

    await (query.message if query else update.message).reply_text("ኳዚ ጀምሯል! 🧠")
    await ask_question(update, context)

# ... (rest of your code remains the same – ask_question, practice mode, answer handling, etc.)

# Just replace the start and start_quiz functions above
# The rest (end_quiz, leaderboard, admin commands, delete, etc.) stay exactly as in your last version
async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data.get('q_index', 0)

    if idx >= len(quiz_questions):
        await end_quiz(update, context)
        return

    q = quiz_questions[idx]
    keyboard = [
        [InlineKeyboardButton(q['A'], callback_data="A")],
        [InlineKeyboardButton(q['B'], callback_data="B")],
        [InlineKeyboardButton(q['C'], callback_data="C")],
        [InlineKeyboardButton(q['D'], callback_data="D")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.reply_text(q["question"], reply_markup=reply_markup)
    else:
        await update.message.reply_text(q["question"], reply_markup=reply_markup)

# ========== PRACTICE MODE ==========
async def start_practice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    if not practice_questions:
        await (query.message if query else update.message).reply_text("No practice questions available yet.")
        return

    user = update.effective_user
    context.user_data.clear()

    context.user_data["mode"] = "practice"
    context.user_data["user_id"] = user.id
    context.user_data["username"] = user.username or str(user.id)

    await ask_practice_question(update, context)

async def ask_practice_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not practice_questions:
        return

    q = random.choice(practice_questions)
    context.user_data["current_q"] = q

    keyboard = [
        [InlineKeyboardButton(q['A'], callback_data="A")],
        [InlineKeyboardButton(q['B'], callback_data="B")],
        [InlineKeyboardButton(q['C'], callback_data="C")],
        [InlineKeyboardButton(q['D'], callback_data="D")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = update.callback_query.message if update.callback_query else update.message
    await message.reply_text(q["question"], reply_markup=reply_markup)

# ========== ANSWER HANDLING ==========
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    mode = context.user_data.get("mode", "quiz")

    if mode == "practice":
        selected = query.data
        q = context.user_data.get("current_q")
        if not q:
            await query.edit_message_text("Session expired. Use /start")
            return

        correct = q["correct"]
        is_correct = selected == correct

        feedback = f"✅ Correct! The answer is {correct}." if is_correct else f"❌ Wrong. The correct answer is {correct}."

        # practice_logs_collection removed → no logging here anymore

        keyboard = [
            [InlineKeyboardButton("Next Question ➡️", callback_data='next_practice')],
            [InlineKeyboardButton("Stop Practice 🛑", callback_data='stop_practice')]
        ]
        await query.edit_message_text(feedback, reply_markup=InlineKeyboardMarkup(keyboard))

    else:  # quiz mode
        idx = context.user_data.get("q_index", 0)
        selected = query.data
        correct = quiz_questions[idx]["correct"]

        if selected == correct:
            context.user_data["score"] = context.user_data.get("score", 0) + 1

        context.user_data["q_index"] = idx + 1
        await ask_question(update, context)

# ========== PRACTICE CONTROLS ==========
async def next_practice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await ask_practice_question(update, context)

async def stop_practice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data.clear()
    await update.callback_query.edit_message_text(
        "Practice session ended.\n\nUse /start to choose Quiz or Practice again."
    )

# ========== QUIZ END & LEADERBOARD ==========
async def end_quiz(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = context.user_data.get("user_id")
    username = context.user_data.get("username")
    score = context.user_data.get("score", 0)
    total = len(quiz_questions)

    if user_id:
        try:
            scores_collection.update_one(
                {"user_id": user_id},
                {"$set": {
                    "username": username,
                    "score": score,
                    "total": total,
                    "timestamp": datetime.utcnow()
                }},
                upsert=True
            )
        except Exception as e:
            logging.error(f"Failed to save score: {e}")

    top_scores = list(scores_collection.find().sort("score", -1).limit(10))
    text = f"Your score: **{score}/{total}**\n\n🏆 Top 10:\n"
    if not top_scores:
        text += "No scores yet."
    else:
        for rank, doc in enumerate(top_scores, 1):
            text += f"{rank}. {doc['username']}: {doc['score']}/{doc['total']}\n"

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.effective_message.reply_text(text, parse_mode="Markdown")

    # Notify admins
    admin_text = f"📈 {username} scored {score}/{total} in quiz"
    for admin_id in admin_ids:
        try:
            await context.bot.send_message(admin_id, admin_text)
        except:
            pass

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top = list(scores_collection.find().sort("score", -1).limit(10))
    if not top:
        await update.message.reply_text("No scores yet.")
        return

    text = "🏆 **Quiz Leaderboard**\n\n"
    for rank, doc in enumerate(top, 1):
        text += f"{rank}. {doc['username']}: {doc['score']}/{doc['total']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

 #clear leaderboard command (admin only)
async def clear_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username not in admin_usernames:
        await update.message.reply_text("Not authorized.")
        return

    scores_collection.delete_many({})
    await update.message.reply_text("✅ Leaderboard cleared.")   

# ========== ADMIN: END CURRENT QUIZ ==========
async def end_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username not in admin_usernames:
        await update.message.reply_text("Not authorized.")
        return

    if not quiz_questions:
        await update.message.reply_text("No active quiz questions to end.")
        return

    count = quiz_questions_collection.count_documents({})
    if count > 0:
        docs = list(quiz_questions_collection.find())
        practice_questions_collection.insert_many(docs)
        quiz_questions_collection.delete_many({})
        load_all_questions()

        await update.message.reply_text(
            f"✅ Quiz ended!\n{len(docs)} questions moved to practice pool."
        )
    else:
        await update.message.reply_text("No questions to move.")

# ========== ADMIN: ADD QUESTIONS ==========
async def add_quiz_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username not in admin_usernames:
        await update.message.reply_text("Not authorized.")
        return ConversationHandler.END

    context.user_data["adding_quiz"] = True
    await update.message.reply_text("📝 Send the **QUIZ** question text:")
    return QUIZ_Q_TEXT

async def add_practice_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username not in admin_usernames:
        await update.message.reply_text("Not authorized.")
        return ConversationHandler.END

    context.user_data["adding_quiz"] = False
    await update.message.reply_text("📝 Send the **PRACTICE** question text:")
    return PRAC_Q_TEXT

async def receive_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q"] = {"question": update.message.text}
    await update.message.reply_text("Send option A:")
    return QUIZ_OPT_A if context.user_data.get("adding_quiz") else PRAC_OPT_A

async def receive_option_a(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q"]["A"] = update.message.text
    await update.message.reply_text("Send option B:")
    return QUIZ_OPT_B if context.user_data.get("adding_quiz") else PRAC_OPT_B

async def receive_option_b(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q"]["B"] = update.message.text
    await update.message.reply_text("Send option C:")
    return QUIZ_OPT_C if context.user_data.get("adding_quiz") else PRAC_OPT_C

async def receive_option_c(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q"]["C"] = update.message.text
    await update.message.reply_text("Send option D:")
    return QUIZ_OPT_D if context.user_data.get("adding_quiz") else PRAC_OPT_D

async def receive_option_d(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q"]["D"] = update.message.text
    await update.message.reply_text("Which is the correct answer? (A, B, C, or D)")
    return QUIZ_CORRECT if context.user_data.get("adding_quiz") else PRAC_CORRECT

async def receive_correct_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    correct = update.message.text.strip().upper()
    if correct not in ['A', 'B', 'C', 'D']:
        await update.message.reply_text("Please enter A, B, C, or D.")
        return QUIZ_CORRECT

    context.user_data["new_q"]["correct"] = correct
    try:
        quiz_questions_collection.insert_one(context.user_data["new_q"])
        load_quiz_questions()
        await update.message.reply_text("✅ Quiz question added! (temporary until /endquiz)")
    except Exception as e:
        await update.message.reply_text(f"Error saving: {e}")

    context.user_data.pop("new_q", None)
    context.user_data.pop("adding_quiz", None)
    return ConversationHandler.END

async def receive_correct_practice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    correct = update.message.text.strip().upper()
    if correct not in ['A', 'B', 'C', 'D']:
        await update.message.reply_text("Please enter A, B, C, or D.")
        return PRAC_CORRECT

    context.user_data["new_q"]["correct"] = correct
    try:
        practice_questions_collection.insert_one(context.user_data["new_q"])
        load_practice_questions()
        await update.message.reply_text("✅ Practice question added permanently!")
    except Exception as e:
        await update.message.reply_text(f"Error saving: {e}")

    context.user_data.pop("new_q", None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Canceled.")
    context.user_data.clear()
    return ConversationHandler.END

# ========== ADMIN DELETE (quiz questions) ==========
async def delete_question_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username not in admin_usernames:
        await update.message.reply_text("Not authorized.")
        return

    all_qs = list(quiz_questions_collection.find())
    if not all_qs:
        await update.message.reply_text("No quiz questions found.")
        return

    for q in all_qs:
        text = f"❓ {q['question']}\nA: {q.get('A','')}\nB: {q.get('B','')}\nC: {q.get('C','')}\nD: {q.get('D','')}\nCorrect: {q.get('correct','')}"
        keyboard = [[InlineKeyboardButton("❌ Delete", callback_data=f"delete_{str(q['_id'])}")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

 #delete practice question
async def delete_practice_question_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username not in admin_usernames:
        await update.message.reply_text("Not authorized.")
        return

    all_qs = list(practice_questions_collection.find())
    if not all_qs:
        await update.message.reply_text("No practice questions found.")
        return

    for q in all_qs:
        text = f"❓ {q['question']}\nA: {q.get('A','')}\nB: {q.get('B','')}\nC: {q.get('C','')}\nD: {q.get('D','')}\nCorrect: {q.get('correct','')}"
        keyboard = [[InlineKeyboardButton("❌ Delete", callback_data=f"delete_practice_{str(q['_id'])}")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))       

async def handle_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    try:
        if data.startswith("delete_practice_"):
            # Extract ID after "delete_practice_"
            q_id = data.split("delete_practice_", 1)[1]
            result = practice_questions_collection.delete_one({"_id": ObjectId(q_id)})
            if result.deleted_count == 1:
                load_practice_questions()
                await query.edit_message_text("✅ Practice question deleted successfully.")
            else:
                await query.edit_message_text("Failed to delete practice question (question not found).")

        elif data.startswith("delete_"):
            # Extract ID after "delete_"
            q_id = data.split("delete_", 1)[1]
            result = quiz_questions_collection.delete_one({"_id": ObjectId(q_id)})
            if result.deleted_count == 1:
                load_quiz_questions()
                await query.edit_message_text("✅ Quiz question deleted successfully.")
            else:
                await query.edit_message_text("Failed to delete quiz question (question not found).")

        else:
            await query.edit_message_text("Invalid delete request.")

    except Exception as e:
        logging.error(f"Delete error: {e}")
        await query.edit_message_text(f"Error during deletion: {str(e)}")
   
# ========== MAIN ==========
def main():
    load_all_questions()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("clearleaderboard", clear_leaderboard))
    app.add_handler(CommandHandler("endquiz", end_quiz_command))

    app.add_handler(CallbackQueryHandler(start_quiz, pattern="^start_quiz$"))
    app.add_handler(CallbackQueryHandler(start_practice, pattern="^start_practice$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^[ABCD]$"))
    app.add_handler(CallbackQueryHandler(next_practice, pattern="^next_practice$"))
    app.add_handler(CallbackQueryHandler(stop_practice, pattern="^stop_practice$"))

    app.add_handler(CommandHandler("deletequizquestion", delete_question_command))
    app.add_handler(CommandHandler("deletepracticequestion", delete_practice_question_command))
    app.add_handler(CallbackQueryHandler(handle_delete_callback, pattern="^(delete_|delete_practice_)"))

    quiz_conv = ConversationHandler(
        entry_points=[CommandHandler("addquiz", add_quiz_start)],
        states={
            QUIZ_Q_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_question)],
            QUIZ_OPT_A: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_a)],
            QUIZ_OPT_B: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_b)],
            QUIZ_OPT_C: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_c)],
            QUIZ_OPT_D: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_d)],
            QUIZ_CORRECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_correct_quiz)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    practice_conv = ConversationHandler(
        entry_points=[CommandHandler("addpractice", add_practice_start)],
        states={
            PRAC_Q_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_question)],
            PRAC_OPT_A: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_a)],
            PRAC_OPT_B: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_b)],
            PRAC_OPT_C: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_c)],
            PRAC_OPT_D: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_d)],
            PRAC_CORRECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_correct_practice)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(quiz_conv)
    app.add_handler(practice_conv)

    print("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
