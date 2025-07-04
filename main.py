import logging
import sqlite3
import os
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# التوكن من المتغيرات البيئية
TOKEN = os.getenv("TOKEN")

# تشغيل اللوجات
logging.basicConfig(level=logging.INFO)

# حالات المستخدمين المؤقتة
user_states = {}

# ✅ إنشاء قاعدة البيانات تلقائيًا
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

# 🚀 الأمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]
    ]
    await update.message.reply_text(
        "أهلاً بيك في وصّلني! اختار نوع الاستخدام:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# 👤 التعامل مع الدور
async def handle_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text == "🚶‍♂️ مستخدم":
        user_states[user_id] = "awaiting_order"
        await update.message.reply_text("اكتب طلبك بالتفصيل (مثال: 1 كيلو طماطم، 2 رغيف)...")
    elif text == "🚚 مندوب":
        await update.message.reply_text("✅ شكرًا لانضمامك كمندوب! هنبعتلك الطلبات القريبة أول ما توصل.")

# 📦 استقبال الطلب
async def handle_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_states.get(user_id) == "awaiting_order":
        conn = sqlite3.connect("wasalny/data.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (user_id, text, status) VALUES (?, ?, ?)", (user_id, text, "قيد الانتظار"))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ تم استلام طلبك: {text}\n📢 جارٍ إرسال الطلب للمناديب...")
        user_states[user_id] = None

# ✅ إعداد التطبيق
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_role))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_order))

# ✅ بدء التشغيل
if __name__ == "__main__":
    init_db()
    app.run_polling()
