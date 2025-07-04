import logging
import sqlite3
import os
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# 🔐 التوكن
TOKEN = "8119170278:AAGfqFrfes_0g-EmbBBk2K6e6DjQflwlBg0"

# 🔧 تهيئة اللوج
logging.basicConfig(level=logging.INFO)

# 🗂️ الحالة المؤقتة للمستخدمين
user_states = {}

# ✅ إنشاء قاعدة البيانات لو مش موجودة
def init_db():
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
    print("✅ قاعدة البيانات تم إنشاؤها أو موجودة فعلاً.")

# 🚀 الأمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]
    ]
    await update.message.reply_text(
        "أهلاً بيك في وصّلني! اختار نوع الاستخدام:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# 🧠 معالجة الرسائل النصية
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # اختيار الدور
    if text == "🚶‍♂️ مستخدم":
        user_states[user_id] = "awaiting_order"
        await update.message.reply_text("اكتب طلبك بالتفصيل (مثال: 1 كيلو طماطم، 2 رغيف)...")

    elif text == "🚚 مندوب":
        await update.message.reply_text("شكرًا لانضمامك كمندوب! هنبعتلك الطلبات القريبة أول ما توصل.")

    # الطلب من المستخدم
    elif user_states.get(user_id) == "awaiting_order":
        order_text = text
        conn = sqlite3.connect("wasalny/data.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (user_id, text, status) VALUES (?, ?, ?)", (user_id, order_text, "قيد الانتظار"))
        conn.commit()
        conn.close()

        user_states[user_id] = None
        await update.message.reply_text(f"✅ تم استلام طلبك: {order_text}\n📢 جارٍ إرسال الطلب للمناديب...")

    else:
        await update.message.reply_text("اكتب /start وابدأ من جديد ✨")

# 🔁 تشغيل البوت
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

if __name__ == "__main__"
