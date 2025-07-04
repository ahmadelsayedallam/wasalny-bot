import logging
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = "8119170278:AAGfqFrfes_0g-EmbBBk2K6e6DjQflwlBg0"

logging.basicConfig(level=logging.INFO)

user_states = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]
    ]
    await update.message.reply_text(
        "أهلاً بيك في وصّلني! اختار نوع الاستخدام:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text == "🚶‍♂️ مستخدم":
        user_states[user_id] = "awaiting_order"
        await update.message.reply_text("اكتب طلبك بالتفصيل (مثال: 1 كيلو طماطم، 2 رغيف)...")
    elif text == "🚚 مندوب":
        await update.message.reply_text("شكرًا لانضمامك كمندوب! هيوصلك إشعارات لو فيه طلبات قريبة.")

async def handle_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_states.get(user_id) == "awaiting_order":
        order_text = update.message.text
        await update.message.reply_text(f"✅ استلمنا طلبك: {order_text}\nهنبعت الطلب للمناديب القريبين دلوقتي!")
        user_states[user_id] = None  # Reset state

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_role))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_order))

if __name__ == "__main__":
    app.run_polling()
