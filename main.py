import os
import logging
import psycopg2
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, CallbackQueryHandler, filters
)

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)
user_states = {}
user_data = {}

GOVERNORATES = ["الغربية"]
AREAS = [
    "أول طنطا", "ثان طنطا", "حي السيالة", "حي الصاغة", "حي سعيد",
    "شارع البحر", "شارع الحلو", "محطة القطار", "موقف الجلاء"
]

PRICE_OPTIONS = ["10 جنيه", "15 جنيه", "20 جنيه"]
TIME_OPTIONS = ["10 دقايق", "15 دقيقه", "30 دقيقه"]


def get_conn():
    return psycopg2.connect(DATABASE_URL)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [[KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]]
    await update.message.reply_text("أهلاً بيك! اختار دورك:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    user_states[user_id] = None

async def handle_user_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text == "🚶‍♂️ مستخدم":
        user_states[user_id] = "awaiting_governorate"
        await update.message.reply_text("اختار محافظتك:", reply_markup=ReplyKeyboardMarkup([[g] for g in GOVERNORATES], resize_keyboard=True))
        return

    if user_states.get(user_id) == "awaiting_governorate":
        if text not in GOVERNORATES:
            await update.message.reply_text("❌ اختر محافظة من القائمة.")
            return
        user_data[user_id] = {"governorate": text}
        user_states[user_id] = "awaiting_area"
        await update.message.reply_text("اختار الحي:", reply_markup=ReplyKeyboardMarkup([[a] for a in AREAS], resize_keyboard=True))
        return

    if user_states.get(user_id) == "awaiting_area":
        if text not in AREAS:
            await update.message.reply_text("❌ اختر حي من القائمة.")
            return
        user_data[user_id]["area"] = text
        user_states[user_id] = "awaiting_order"
        await update.message.reply_text("اكتب تفاصيل طلبك:", reply_markup=ReplyKeyboardRemove())
        return

    if user_states.get(user_id) == "awaiting_order":
        order_text = text
        governorate = user_data[user_id]["governorate"]
        area = user_data[user_id]["area"]
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO orders (user_id, governorate, area, text, status)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
            """, (user_id, governorate, area, order_text, "قيد الانتظار"))
            order_id = cur.fetchone()[0]
            conn.commit()

            cur.execute("""
                SELECT user_id FROM agents
                WHERE is_verified = TRUE AND governorate = %s AND area = %s
            """, (governorate, area))
            agents = cur.fetchall()
            cur.close()
            conn.close()

            for (agent_id,) in agents:
                button = InlineKeyboardMarkup([[InlineKeyboardButton("📝 إرسال عرض", callback_data=f"offer_{order_id}")]])
                await context.bot.send_message(
                    chat_id=agent_id,
                    text=f"طلب جديد من {area}:\n{order_text}",
                    reply_markup=button
                )

            await update.message.reply_text("✅ تم تسجيل طلبك! سيتم إرسال الطلب للمناديب القريبين.")
        except Exception as e:
            logging.error(f"❌ فشل حفظ الطلب: {e}")
            await update.message.reply_text("❌ حصل خطأ أثناء تسجيل الطلب.")
        user_states[user_id] = None
        user_data[user_id] = {}
        return

    if text == "🚚 مندوب":
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT is_verified FROM agents WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()

            if row:
                if row[0]:
                    await update.message.reply_text("✅ تم تفعيل حسابك كمندوب.")
                else:
                    await update.message.reply_text("⏳ طلبك قيد المراجعة.")
                return
        except Exception as e:
            logging.error(f"❌ فشل التحقق من حالة المندوب: {e}")

        user_states[user_id] = "awaiting_agent_name"
        await update.message.reply_text("اكتب اسمك الكامل:")
        return

    if user_states.get(user_id) == "awaiting_agent_name":
        user_data[user_id] = {"full_name": text}
        user_states[user_id] = "awaiting_agent_governorate"
        await update.message.reply_text("اختار محافظتك:", reply_markup=ReplyKeyboardMarkup([[g] for g in GOVERNORATES], resize_keyboard=True))
        return

    if user_states.get(user_id) == "awaiting_agent_governorate":
        if text not in GOVERNORATES:
            await update.message.reply_text("❌ اختر محافظة من القائمة.")
            return
        user_data[user_id]["governorate"] = text
        user_states[user_id] = "awaiting_agent_area"
        await update.message.reply_text("اختار الحي:", reply_markup=ReplyKeyboardMarkup([[a] for a in AREAS], resize_keyboard=True))
        return

    if user_states.get(user_id) == "awaiting_agent_area":
        if text not in AREAS:
            await update.message.reply_text("❌ اختر حي من القائمة.")
            return
        user_data[user_id]["area"] = text
        user_states[user_id] = "awaiting_id_photo"
        await update.message.reply_text("📸 ارفع صورة بطاقتك لمراجعتها قبل التفعيل.")
        return

    await update.message.reply_text("من فضلك ابدأ بـ /start")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_states.get(user_id) == "awaiting_id_photo":
        file_id = update.message.photo[-1].file_id
        full_name = user_data[user_id].get("full_name")
        governorate = user_data[user_id].get("governorate")
        area = user_data[user_id].get("area")

        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO agents (user_id, full_name, governorate, area, id_photo_file_id, is_verified)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, full_name, governorate, area, file_id, False))
            conn.commit()
            cur.close()
            conn.close()
            await update.message.reply_text("✅ تم استلام البطاقة. سيتم مراجعتها من الإدارة قبل تفعيل حسابك.")
        except Exception as e:
            logging.error(f"❌ فشل حفظ بيانات المندوب: {e}")
            await update.message.reply_text("❌ حصل خطأ أثناء حفظ البيانات.")
        user_states[user_id] = None
        user_data[user_id] = {}

async def handle_offer_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("offer_"):
        order_id = int(data.split("_")[1])
        user_id = query.from_user.id
        user_data[user_id] = {"order_id": order_id}
        user_states[user_id] = "awaiting_offer_price"
        keyboard = [[InlineKeyboardButton(price, callback_data=f"price_{price}")] for price in PRICE_OPTIONS]
        await query.message.reply_text("اختار السعر المناسب:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("price_"):
        price = data.split("_")[1]
        user_id = update.effective_user.id
        user_data[user_id]["price"] = price
        user_states[user_id] = "awaiting_offer_time"
        keyboard = [[InlineKeyboardButton(time, callback_data=f"time_{time}")] for time in TIME_OPTIONS]
        await query.message.reply_text("اختار الوقت المتوقع للتوصيل:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("time_"):
        time = data.split("_")[1]
        user_id = update.effective_user.id
        offer = user_data.get(user_id, {})
        order_id = offer.get("order_id")
        price = offer.get("price")

        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO offers (order_id, agent_id, price, estimated_time)
                VALUES (%s, %s, %s, %s)
            """, (order_id, user_id, price, time))
            conn.commit()
            cur.close()
            conn.close()
            await update.callback_query.message.reply_text("✅ تم إرسال عرضك بنجاح!")
        except Exception as e:
            logging.error(f"❌ فشل حفظ العرض: {e}")
            await update.callback_query.message.reply_text("❌ حصل خطأ أثناء حفظ العرض.")
        user_states[user_id] = None
        user_data[user_id] = {}

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_role))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_offer_button))
    app.run_polling()
