
import logging, sqlite3, os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8039901966:AAFxwP_rEjGBR-xTOQ8351WfZ2L5RXWXrvc"

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_path = "wasalny/data.db"
    if not os.path.exists(db_path):
        await update.message.reply_text("🚫 قاعدة البيانات غير موجودة!")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, text, status FROM orders")
        orders = cursor.fetchall()
        conn.close()

        if not orders:
            await update.message.reply_text("🚫 لا يوجد طلبات حتى الآن.")
            return

        msg = "📋 الطلبات الحالية:

"
        for o in orders:
            msg += f"📦 #{o[0]} - الحالة: {o[3]}
👤 المستخدم: {o[1]}
📝 الطلب: {o[2]}

"

        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ أثناء تحميل الطلبات:\n{e}")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))

if __name__ == "__main__":
    app.run_polling()
