import sqlite3
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# اضبط التوكن هنا أو استخدم متغير بيئة
BOT_TOKEN_ADMIN = "8039901966:AAFx8Mp0v33CSro0Ii5Im0howXpl99EUCCg"

# مسار ملف قاعدة البيانات
DB_PATH = "wasalny.db"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, user_id, order_text, status FROM orders ORDER BY id DESC LIMIT 10")
    orders = cursor.fetchall()
    conn.close()

    if not orders:
        await update.message.reply_text("مافيش طلبات حتى الآن.")
        return

    message = "📝 *الطلبات الأخيرة:*\n\n"
    for order in orders:
        order_id, user_id, order_text, status = order
        message += f"#{order_id} - مستخدم: {user_id}\nالطلب: {order_text}\nالحالة: {status}\n\n"

    await update.message.reply_text(message, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "/start - عرض الطلبات الأخيرة\n"
        "/help - هذه الرسالة\n"
        # ممكن تضيف أوامر تانية هنا حسب الحاجة
    )
    await update.message.reply_text(help_text)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN_ADMIN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    print("بوت الإدارة شغال...")
    app.run_polling()

if __name__ == "__main__":
    main()
