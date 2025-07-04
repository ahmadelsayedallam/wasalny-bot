import logging
import os
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN_ADMIN = os.getenv("BOT_TOKEN_ADMIN")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)

def create_tables():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'قيد الانتظار'
        )
        """)
        conn.commit()
        cursor.close()
        conn.close()
        logging.info("✅ جدول orders موجود أو تم إنشاؤه بنجاح.")
    except Exception as e:
        logging.error(f"❌ فشل إنشاء جدول orders: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute("SELECT id, user_id, text, status FROM orders ORDER BY id DESC LIMIT 10")
    orders = cursor.fetchall()
    cursor.close()
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
        "/help - هذه الرسالة"
    )
    await update.message.reply_text(help_text)

def main():
    create_tables()
    app = ApplicationBuilder().token(BOT_TOKEN_ADMIN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    logging.info("بوت الإدارة شغال...")
    app.run_polling()

if __name__ == "__main__":
    main()
