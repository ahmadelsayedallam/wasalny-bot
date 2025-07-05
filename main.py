import os
import logging
import psycopg2
import httpx
import cloudinary
import cloudinary.uploader
from telegram import (
    Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# إعداد البيئة
TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

logging.basicConfig(level=logging.INFO)
user_states, user_data = {}, {}

GOVS = ["الغربية"]
AREAS = ["أول طنطا", "ثان طنطا", "حي السيالة", "حي الصاغة", "حي سعيد",
         "شارع البحر", "شارع الحلو", "محطة القطار", "موقف الجلاء"]
PRICE_OPTS = ["10 جنيه", "15 جنيه", "20 جنيه"]
TIME_OPTS = ["10 دقايق", "15 دقيقه", "30 دقيقه"]

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# بدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    keyboard = [[KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]]
    await update.message.reply_text("أهلاً بيك! اختار دورك:", reply_markup=ReplyKeyboardMarkup(keyboard, True))
    user_states[uid] = None

# التعامل مع النصوص حسب الحالة
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text
    st = user_states.get(uid)

    if txt == "🚶‍♂️ مستخدم":
        user_states[uid] = "awaiting_governorate"
        return await update.message.reply_text("اختار محافظتك:", reply_markup=ReplyKeyboardMarkup([[g] for g in GOVS], True))

    if st == "awaiting_governorate":
        if txt not in GOVS: return await update.message.reply_text("❌ اختر من القائمة.")
        user_data[uid] = {"governorate": txt}
        user_states[uid] = "awaiting_area"
        return await update.message.reply_text("اختار الحي:", reply_markup=ReplyKeyboardMarkup([[a] for a in AREAS], True))

    if st == "awaiting_area":
        if txt not in AREAS: return await update.message.reply_text("❌ اختر من القائمة.")
        user_data[uid]["area"] = txt
        user_states[uid] = "awaiting_order"
        return await update.message.reply_text("اكتب تفاصيل طلبك:", reply_markup=ReplyKeyboardRemove())

    if st == "awaiting_order":
        od = txt
        gov, area = user_data[uid]["governorate"], user_data[uid]["area"]
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("INSERT INTO orders (user_id, governorate, area, text, status) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                        (uid, gov, area, od, "قيد الانتظار"))
            oid = cur.fetchone()[0]
            conn.commit()

            cur.execute("SELECT user_id FROM agents WHERE is_verified=TRUE AND governorate=%s AND area=%s", (gov, area))
            agents = cur.fetchall()
            conn.close()

            for (aid,) in agents:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("📝 عرض", callback_data=f"offer_{oid}")]])
                await context.bot.send_message(chat_id=aid, text=f"طلب جديد من {area}:\n{od}", reply_markup=kb)

            await update.message.reply_text("✅ تم إرسال الطلب للمندوبين. انتظر العروض.")
        except Exception as e:
            logging.error(e)
            await update.message.reply_text("❌ خطأ في تسجيل الطلب.")

        user_states[uid] = None
        user_data[uid] = {}
        return

    if txt == "🚚 مندوب":
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT is_verified FROM agents WHERE user_id=%s", (uid,))
            row = cur.fetchone()
            conn.close()
            if row:
                return await update.message.reply_text("✅ تم قبولك كمندوب." if row[0] else "⏳ في انتظار المراجعة.")
        except Exception as e:
            logging.error(e)
        user_states[uid] = "awaiting_agent_name"
        return await update.message.reply_text("اكتب اسمك الكامل:")

    if st == "awaiting_agent_name":
        user_data[uid] = {"full_name": txt}
        user_states[uid] = "awaiting_agent_governorate"
        return await update.message.reply_text("اختار محافظتك:", reply_markup=ReplyKeyboardMarkup([[g] for g in GOVS], True))

    if st == "awaiting_agent_governorate":
        if txt not in GOVS: return await update.message.reply_text("❌ اختر من القائمة.")
        user_data[uid]["governorate"] = txt
        user_states[uid] = "awaiting_agent_area"
        return await update.message.reply_text("اختار الحي:", reply_markup=ReplyKeyboardMarkup([[a] for a in AREAS], True))

    if st == "awaiting_agent_area":
        if txt not in AREAS: return await update.message.reply_text("❌ اختر من القائمة.")
        user_data[uid]["area"] = txt
        user_states[uid] = "awaiting_id_photo"
        return await update.message.reply_text("📸 ارفع صورة بطاقتك:")

    await update.message.reply_text("❗ استخدم /start لإعادة البداية.")

# رفع صورة البطاقة
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if user_states.get(uid) == "awaiting_id_photo":
        try:
            file = await context.bot.get_file(update.message.photo[-1].file_id)
            url = file.file_path
            async with httpx.AsyncClient() as c:
                resp = await c.get(url)
                result = cloudinary.uploader.upload(resp.content)
                photo_url = result["secure_url"]

            d = user_data[uid]
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("INSERT INTO agents (user_id, full_name, governorate, area, id_photo_url, is_verified) VALUES (%s,%s,%s,%s,%s,FALSE)",
                        (uid, d["full_name"], d["governorate"], d["area"], photo_url))
            conn.commit()
            conn.close()

            await update.message.reply_text("✅ تم إرسال البيانات. انتظر مراجعة الإدارة.")
        except Exception as e:
            logging.error(e)
            await update.message.reply_text("❌ حدث خطأ أثناء حفظ البيانات.")
        user_states[uid] = None
        user_data[uid] = {}

# تعامل المندوب مع الزرار
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    if data.startswith("offer_"):
        oid = int(data.split("_")[1])
        user_data[uid] = {"order_id": oid}
        user_states[uid] = "awaiting_offer_price"
        kb = [[InlineKeyboardButton(p, callback_data=f"price_{p}")] for p in PRICE_OPTS]
        return await query.message.reply_text("اختار السعر:", reply_markup=InlineKeyboardMarkup(kb))

    if data.startswith("price_"):
        price = data.split("_")[1]
        user_data[uid]["price"] = price
        user_states[uid] = "awaiting_offer_time"
        kb = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in TIME_OPTS]
        return await query.message.reply_text("اختار الزمن:", reply_markup=InlineKeyboardMarkup(kb))

    if data.startswith("time_"):
        time = data.split("_")[1]
        info = user_data.get(uid, {})
        oid = info["order_id"]
        price = info["price"]
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("INSERT INTO offers (order_id, agent_id, price, estimated_time) VALUES (%s, %s, %s, %s)",
                        (oid, uid, price, time))
            conn.commit()

            # إرسال العروض للمستخدم
            cur.execute("SELECT user_id FROM orders WHERE id=%s", (oid,))
            user_id = cur.fetchone()[0]
            cur.execute("SELECT full_name FROM agents WHERE user_id=%s", (uid,))
            agent_name = cur.fetchone()[0]

            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ قبول", callback_data=f"accept_{oid}_{uid}"),
                InlineKeyboardButton("❌ رفض", callback_data=f"reject_{oid}_{uid}")
            ]])

            msg = f"📦 عرض جديد من {agent_name}\n💰 السعر: {price}\n⏱️ الزمن: {time}"
            await context.bot.send_message(chat_id=user_id, text=msg, reply_markup=kb)
            conn.close()

            await query.message.reply_text("✅ تم إرسال العرض.")
        except Exception as e:
            logging.error(e)
            await query.message.reply_text("❌ فشل في إرسال العرض.")

        user_states[uid] = None
        user_data[uid] = {}

# تشغيل البوت
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling()
