import logging, sqlite3
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import os
TOKEN = os.getenv("TOKEN")
logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        msg += f"📦 #{o[0]} - الحالة: {o[3]}\n👤 المستخدم: {o[1]}\n📝 الطلب: {o[2]}\n\n"

    await update.message.reply_text(msg)

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))

if __name__ == "__main__":
    app.run_polling()
