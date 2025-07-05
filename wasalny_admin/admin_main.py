import logging
import os
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# 🛡️ التوكن والداتابيز
TOKEN = os.getenv("BOT_TOKEN_ADMIN")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # هات آخر 10 طلبات
        cursor.execute("""
            SELECT id, user_id, governorate, text, status
            FROM orders
            ORDER BY id DESC
            LIMIT 10
        """)
        orders = cursor.fetchall()

        if not orders:
            await update.message.reply_text("📭 لا يوجد طلبات حالياً.")
            return

        full_message = "📋 آخر الطلبات:\n\n"
        for order in orders:
            order_id, user_id, governorate, text, status = order

            # هات العروض المرتبطة بالطلب
            cursor.execute("""
                SELECT agent_id, price, eta, status
                FROM offers
                WHERE order_id = %s
            """, (order_id,))
            offers = cursor.fetchall()

            order_msg = f"""📦 طلب رقم #{order_id}
🧍 المستخدم: {user_id}
📍 المحافظة: {governorate}
📃 الطلب: {text}
📌 الحالة: {status}
"""

            if offers:
                order_msg += "💬 العروض:\n"
                for offer in offers:
                    agent_id, price, eta, offer_status = offer
                    symbol = "✅" if offer_status == "تم الاختيار" else "❌" if offer_status == "مرفوض" else "⏳"
                    order_msg += f"- 🛵 مندوب {agent_id}: {price} جنيه / {eta} دقيقة {symbol} ({offer_status})\n"
            else:
                order_msg += "🚫 لا توجد عروض حتى الآن.\n"

            order_msg += "\n" + ("-"*30) + "\n"
            full_message += order_msg

        await update.message.reply_text(full_message[:4000])  # عشان مايتخطاش حد تليجرام

        conn.close()
    except Exception as e:
        logging.error(f"❌ فشل في عرض الطلبات: {e}")
        await update.message.reply_text("❌ حصل خطأ أثناء تحميل الطلبات.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    logging.info("🚀 بوت الإدارة شغال...")
    app.run_polling()

if __name__ == "__main__":
    main()
