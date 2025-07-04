import logging
import sqlite3
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# 🔐 توكن بوت الأدمن (بدّله بتاعك الحقيقي)
TOKEN = "8039901966:AAFxwP_rEjGBR-xTOQ8351WfZ2L5RXWXrvc"

# 🔧 إعدادات اللوج
logging.basicConfig(level=logging.INFO)

# 🟩 أمر /start لعرض الطلبات
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = sqlite3.connect("wasalny/data.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, text, status FROM orders")
        orders = cursor.fetchall()
        conn.close()

        if not orders:
            await update.message.reply_text("🚫 لا يوجد طلبات حتى الآن.")
            return

        msg = "📋 الطلبات الحالية:\n\n"
        for o in orders:
            msg += (
                f"📦 طلب رقم #{o[0]}\n"
                f"👤 المستخدم: {o[1]}\n"
                f"📝 الطلب: {o[2]}\n"
                f"📌 الحالة: {o[3]}\n\n"
            )

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text("⚠️ حصل خطأ أثناء تحميل الطلبات.")
        logging.error(f"Error fetching orders: {e}")

# 🚀 تشغيل البوت
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))

if __name__ == "__main__":
    app.run_polling()
