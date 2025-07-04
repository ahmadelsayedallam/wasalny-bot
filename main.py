import logging
import sqlite3
import os
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# توكن البوت
TOKEN = "8119170278:AAFQ_orcaoQL0wKVqtqXchxcivip6qBEo3Q"

# اللوج
logging.basicConfig(level=logging.INFO)

# حالات المستخدمين المؤقتة
user_states = {}

# إنشاء قاعدة البيانات لو مش موجودة
def init_db():
    os.makedirs("wasalny", exist_ok=True)
    conn = sqlite3.connect("wasalny/data.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()

# أمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]]
    await update.message.reply_text(
        "أهلاً بيك في وصّلني! اختار نوع الاستخدام:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# التعامل مع اختيار الدور
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text == "🚶‍♂️ مستخدم":
        user_states[user_id] = "awaiting_order"
        await update.message.reply_text("📝 من فضلك اكتب طلبك بالتفصيل (مثال: 1 كيلو طماطم، 2 عيش بلدي)...")

    elif text == "🚚 مندوب":
        await update.message.reply_text("✅ تم تسجيلك كمندوب! هيوصلك إشعارات بالطلبات الجديدة أول ما توصل.")

    elif user_states.get(user_id) == "awaiting_order":
        # تخزين الطلب في قاعدة البيانات
        conn = sqlite3.connect("wasalny/data.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (user_id, text, status) VALUES (?, ?, ?)", (user_id, text, "قيد الانتظار"))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ تم استلام طلبك: {text}\n📢 جارٍ إرسال الطلب للمناديب...")
        user_states[user_id] = None

    else:
        await update.message.reply_text("📌 من فضلك اختار دورك أولًا بالضغط على /start")

# تشغيل التطبيق
if __name__ == "__main__":
    init_db()
    app.run_polling()
