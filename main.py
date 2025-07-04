import logging
import os
import psycopg2
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)
user_states = {}

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
    keyboard = [[KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]]
    await update.message.reply_text("أهلاً بيك! اختار دورك:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text == "🚶‍♂️ مستخدم":
        user_states[user_id] = "awaiting_order"
        await update.message.reply_text("اكتب طلبك بالتفصيل (مثل: 1 كيلو طماطم)...")
        return

    if user_states.get(user_id) == "awaiting_order":
        order = text
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO orders (user_id, text, status) VALUES (%s, %s, %s)",
                (user_id, order, "قيد الانتظار")
            )
            conn.commit()
            cursor.close()
            conn.close()
            logging.info(f"✅ تم حفظ الطلب للمستخدم {user_id}: {order}")
            await update.message.reply_text(f"✅ تم استلام طلبك: {order}\n📢 جارٍ إرسال الطلب للمناديب...")
        except Exception as e:
            logging.error(f"❌ فشل حفظ الطلب: {e}")
            await update.message.reply_text("❌ عذراً، حصل خطأ أثناء حفظ طلبك.")
        user_states[user_id] = None
        return

    if text == "🚚 مندوب":
        await update.message.reply_text("✅ تم تسجيلك كمندوب! هتوصلك الطلبات قريب.")
        return

    await update.message.reply_text("من فضلك اكتب /start للاختيار")

def main():
    create_tables()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logging.info("بوت المستخدم شغال...")
    app.run_polling()

if __name__ == "__main__":
    main()
