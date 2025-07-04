import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8039901966:AAFxwP_rEjGBR-xTOQ8351WfZ2L5RXWXrvc"

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بيك في لوحة تحكم وصّلني 👨‍💼\nجارٍ تجهيز عرض الطلبات...")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))

if __name__ == "__main__":
    app.run_polling()
