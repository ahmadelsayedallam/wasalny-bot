import logging
import sqlite3
import os
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# استخدام التوكن من متغير البيئة أو القيمة الثابتة
TOKEN = os.getenv("TOKEN", "8119170278:AAFQ_orcaoQL0wKVqtqXchxcivip6qBEo3Q")

logging.basicConfig(level=logging.INFO)
user_states = {}

def init_db():
    try:
        os.makedirs("wasalny", exist_ok=True)
        conn = sqlite3.connect("wasalny/data.db")
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT,
                status TEXT
            )
        ''')
        conn.commit()
        conn.close()
        logging.info("✅ جدول orders جاهز أو متواجد بالفعل.")
    except Exception as e:
        logging.error(f"❌ خطأ أثناء إنشاء قاعدة البيانات: {e}")

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
            conn = sqlite3.connect("wasalny/data.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO orders (user_id, text, status) VALUES (?, ?, ?)", (user_id, order, "قيد الانتظار"))
            conn.commit()
            conn.close()
            logging.info("✅ تم حفظ الطلب في القاعدة.")
            await update.message.reply_text(f"✅ استلمنا طلبك: {order}")
        except Exception as e:
            logging.error(f"❌ فشل حفظ الطلب: {e}")
            await update.message.reply_text("عذراً، فشل حفظ طلبك. حاول مرة تانية.")
        user_states[user_id] = None
        return

    if text == "🚚 مندوب":
        await update.message.reply_text("✅ تم تسجيلك كمندوب! هتوصلك الطلبات قريب.")
        return

    await update.message.reply_text("من فضلك اكتب /start للاختيار")

if __name__ == "__main__":
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
