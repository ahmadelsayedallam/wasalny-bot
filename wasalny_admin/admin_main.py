import logging
import os
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN_ADMIN = os.getenv("BOT_TOKEN_ADMIN")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute("SELECT id, user_id, governorate, text, status FROM orders ORDER BY id DESC LIMIT 10")
        orders = cursor.fetchall()
        if not orders:
            await update.message.reply_text("❌ لا يوجد طلبات حتى الآن.")
            return

        msg = "📋 آخر 10 طلبات:\n\n"
        for order in orders:
            msg += f"🆔 الطلب: {order[0]}\n"
            msg += f"👤 المستخدم: {order[1]}\n"
            msg += f"📍 المحافظة: {order[2]}\n"
            msg += f"📦 الطلب: {order[3]}\n"
            msg += f"📌 الحالة: {order[4]}\n"
            msg += "------------------------\n"

            cursor.execute("SELECT agent_id, price, eta FROM offers WHERE order_id = %s", (order[0],))
            offers = cursor.fetchall()
            if offers:
                msg += "💬 العروض:\n"
                for offer in offers:
                    msg += f"🧍‍♂️ مندوب: {offer[0]} | 💵 السعر: {offer[1]} | ⏱️ الوقت: {offer[2]}\n"
            else:
                msg += "❌ لا توجد عروض بعد.\n"

            msg += "========================\n\n"

        await update.message.reply_text(msg[:4000])

        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ فشل عرض الطلبات: {e}")
        await update.message.reply_text("❌ حصل خطأ أثناء استعراض الطلبات.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN_ADMIN).build()
    app.add_handler(CommandHandler("start", start))
    logging.info("📊 بوت الإدارة شغال...")
    app.run_polling()

if __name__ == "__main__":
    main()
