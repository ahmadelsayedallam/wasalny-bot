import logging
import os
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("ADMIN_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)

# حالة انتظار اختيار عرض من العميل: user_id -> order_id
client_waiting_choice = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك في لوحة إدارة وصّلني.\nاستخدم الأمر /orders لعرض آخر الطلبات.")

async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, governorate, text, status FROM orders ORDER BY id DESC LIMIT 10")
        orders = cursor.fetchall()
        cursor.close()
        conn.close()

        if not orders:
            await update.message.reply_text("لا توجد طلبات حالياً.")
            return

        for order in orders:
            order_id, user_id, governorate, text, status = order
            msg = (f"🆔 طلب رقم: {order_id}\n"
                   f"👤 المستخدم: {user_id}\n"
                   f"🏙 المحافظة: {governorate}\n"
                   f"📦 الطلب: {text}\n"
                   f"📌 الحالة: {status}")

            keyboard = []
            if status == "قيد الانتظار":
                keyboard = [
                    [InlineKeyboardButton("عرض العروض", callback_data=f"show_offers_{order_id}")]
                ]

            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

    except Exception as e:
        logging.error(f"❌ خطأ في جلب الطلبات: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء جلب الطلبات.")

async def show_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split("_")[-1])

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT id, agent_id, price, eta, status FROM offers WHERE order_id = %s", (order_id,))
        offers = cursor.fetchall()
        cursor.close()
        conn.close()

        if not offers:
            await query.message.reply_text("لا توجد عروض لهذا الطلب.")
            return

        buttons = []
        msg = f"عروض الطلب رقم {order_id}:\n\n"
        for offer in offers:
            offer_id, agent_id, price, eta, status = offer
            msg += f"🆔 عرض رقم: {offer_id}\nمندوب: {agent_id}\nالسعر: {price} جنيه\nالوقت: {eta}\nالحالة: {status}\n\n"
            if status == "قيد الانتظار":
                buttons.append([InlineKeyboardButton(f"اختيار عرض {offer_id}", callback_data=f"choose_offer_{offer_id}_{order_id}")])

        await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons))

    except Exception as e:
        logging.error(f"❌ خطأ في جلب العروض: {e}")
        await query.message.reply_text("❌ حدث خطأ أثناء جلب العروض.")

async def choose_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("_")
    offer_id = int(data[2])
    order_id = int(data[3])

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        # تحديث حالة العرض إلى "تم الاختيار"
        cursor.execute("UPDATE offers SET status = 'تم الاختيار' WHERE id = %s", (offer_id,))

        # تحديث حالة الطلب إلى "قيد التنفيذ"
        cursor.execute("UPDATE orders SET status = 'قيد التنفيذ' WHERE id = %s", (order_id,))

        # إلغاء باقي العروض الأخرى لنفس الطلب
        cursor.execute("UPDATE offers SET status = 'مرفوض' WHERE order_id = %s AND id != %s", (order_id, offer_id))

        conn.commit()
        cursor.close()
        conn.close()

        await query.message.reply_text(f"✅ تم اختيار العرض رقم {offer_id} وتم تحديث حالة الطلب إلى قيد التنفيذ.")

    except Exception as e:
        logging.error(f"❌ خطأ في اختيار العرض: {e}")
        await query.message.reply_text("❌ حدث خطأ أثناء اختيار العرض.")

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("الأمر غير معروف. استخدم /orders لعرض الطلبات.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("orders", list_orders))
    app.add_handler(CallbackQueryHandler(show_offers, pattern=r"^show_offers_\d+$"))
    app.add_handler(CallbackQueryHandler(choice := choose_offer, pattern=r"^choose_offer_\d+_\d+$"))
    app.add_handler(CommandHandler(None, unknown_command))
    logging.info("🛠️ بوت الإدارة شغال...")
    app.run_polling()

if __name__ == "__main__":
    main()
