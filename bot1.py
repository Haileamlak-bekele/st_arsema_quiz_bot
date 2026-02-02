from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters,
    ConversationHandler
)
import logging
from pymongo import MongoClient

logging.basicConfig(level=logging.INFO)

MONGO_URI = "mongodb+srv://quize_admin:mypassword123@cluster0.vispyak.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client.quizdb
questions_collection = db.questions

QUESTION_TEXT, OPTION_A, OPTION_B, OPTION_C, OPTION_D, CORRECT_ANSWER = range(
    6)

questions = []
user_scores = {}
admin_usernames = ['AmHBbe', 'yeabayras', 'Am21HB6']
admin_ids = [1152440268, 7209995991]
summary = "📊 *Quiz Results Summary:*\n\n"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(
        "Start Quiz 🧠", callback_data='start_quiz')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "እንኳን ወደ ቅድስት አርሴማ የመጽሐፍ ቅዱስ ጥናት እራስን መፈተሻ bot በሰላም መጡ!!!",
        reply_markup=reply_markup
    )


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data["score"] = 0
    context.user_data["q_index"] = 0
    context.user_data["username"] = user.username or str(user.id)
    await ask_question(update, context)


async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data.get('q_index', 0)

    if idx >= len(questions):
        if update.callback_query:
            await end_quiz(update.callback_query, context)
        elif update.message:
            await end_quiz(update.message, context)
        return

    q = questions[idx]
    keyboard = [
        [InlineKeyboardButton(q['A'], callback_data="A")],
        [InlineKeyboardButton(q['B'], callback_data="B")],
        [InlineKeyboardButton(q['C'], callback_data="C")],
        [InlineKeyboardButton(q['D'], callback_data="D")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(q["question"], reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(q["question"], reply_markup=reply_markup)


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    username = context.user_data["username"]
    idx = context.user_data["q_index"]
    selected = query.data
    correct = questions[idx]["correct"]

    if selected == correct:
        context.user_data["score"] += 1

    context.user_data["q_index"] += 1
    await ask_question(update, context)


async def end_quiz(update, context: ContextTypes.DEFAULT_TYPE):
    username = context.user_data["username"]
    score = context.user_data["score"]
    total = len(questions)
    user_scores[username] = score

    text = f"{username}, your score is {score}/{total}\n\n🏆 Ranking:"
    sorted_scores = sorted(user_scores.items(),
                           key=lambda x: x[1], reverse=True)
    for rank, (user, s) in enumerate(sorted_scores, 1):
        text += f"\n{rank}. {user}: {s}"

    if hasattr(update, 'edit_text'):
        await update.edit_text(text)
    elif hasattr(update, 'message'):
        await update.message.reply_text(text)

    for admin_id in admin_ids:
        try:
            await context.bot.send_message(chat_id=admin_id, text=f"📈 {username} scored {score}/{total}\n {sorted_scores}")
        except Exception as e:
            logging.warning(f"Couldn't send to admin {admin_id}: {e}")


async def add_question_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username not in admin_usernames:
        await update.message.reply_text(" You are not authorized to add questions.")
        return ConversationHandler.END

    await update.message.reply_text("📝 hi admin, please Send the question text:")
    return QUESTION_TEXT


async def receive_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q"] = {"question": update.message.text}
    await update.message.reply_text("Send option A:")
    return OPTION_A


async def receive_option_a(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q"]["A"] = update.message.text
    await update.message.reply_text("Send option B:")
    return OPTION_B


async def receive_option_b(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q"]["B"] = update.message.text
    await update.message.reply_text("Send option C:")
    return OPTION_C


async def receive_option_c(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q"]["C"] = update.message.text
    await update.message.reply_text("Send option D:")
    return OPTION_D


async def receive_option_d(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q"]["D"] = update.message.text
    await update.message.reply_text("Which is the correct answer? (A, B, C, or D)")
    return CORRECT_ANSWER


async def receive_correct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    correct = update.message.text.upper()
    if correct not in ['A', 'B', 'C', 'D']:
        await update.message.reply_text("Invalid. Please enter A, B, C, or D.")
        return CORRECT_ANSWER

    context.user_data["new_q"]["correct"] = correct
    questions.append(context.user_data["new_q"])

    try:
        questions_collection.insert_one(context.user_data["new_q"])
        await update.message.reply_text("✅ Question added successfully and saved to database!")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Question added locally, but failed to save to database: {e}")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Question creation canceled.")
    return ConversationHandler.END


def load_questions_from_db():
    questions.clear()
    for q in questions_collection.find():
        q.pop('_id', None)
        questions.append(q)

# ✅ NEW FUNCTION: Admin deletes question


async def delete_question_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username not in admin_usernames:
        await update.message.reply_text("You are not authorized to delete questions.")
        return

    all_qs = list(questions_collection.find())
    if not all_qs:
        await update.message.reply_text("No questions found in the database.")
        return

    for q in all_qs:
        q_id = str(q['_id'])
        text = f"❓ {q['question']}\nA. {q['A']}\nB. {q['B']}\nC. {q['C']}\nD. {q['D']}\n✅ {q['correct']}"
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Delete", callback_data=f"delete_{q_id}")]])
        await update.message.reply_text(text, reply_markup=keyboard)


async def handle_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("delete_"):
        q_id = data.split("_", 1)[1]
        from bson import ObjectId
        result = questions_collection.delete_one({"_id": ObjectId(q_id)})
        if result.deleted_count == 1:
            await query.edit_message_text("✅ Question deleted from database.")
            load_questions_from_db()  # reload local copy
        else:
            await query.edit_message_text("⚠️ Failed to delete question.")


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Works for messages and callback queries
    user = update.effective_user or (
        update.callback_query.from_user if update.callback_query else None)
    if not user:
        await update.message.reply_text("Could not determine user.")
        return
    uid = user.id
    uname = user.username or "no username"
    await (update.message.reply_text if getattr(update, "message", None) else update.callback_query.message.reply_text)(
        f"Your ID: {uid}\nUsername: @{uname}"
    )


def main():
    load_questions_from_db()
    app = Application.builder().token(
        "8163769835:AAGJvltV1Pb4orjXbRooqXF0Dk18U5Ub7Rc").build()

    app.add_handler(CommandHandler("myid", myid))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(
        lambda u, c: quiz(u, c), pattern="^start_quiz$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^[ABCD]$"))
    app.add_handler(CommandHandler("deletequestion", delete_question_command))
    app.add_handler(CallbackQueryHandler(
        handle_delete_callback, pattern="^delete_"))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addquestion", add_question_start)],
        states={
            QUESTION_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_question)],
            OPTION_A: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_a)],
            OPTION_B: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_b)],
            OPTION_C: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_c)],
            OPTION_D: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_d)],
            CORRECT_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_correct)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
