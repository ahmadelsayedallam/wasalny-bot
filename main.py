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
    user_id = update.effective_user.id
    keyboard = [[KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]]
    await update.message.reply_text("أهلاً بيك! اختار دورك:", reply_markup=ReplyKeyboardMarkup(keyboard, True))
    user_states[user_id] = None

# معالجة اختيار الدور والطلبات والتسجيل
async def handle_user_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text
    st = user_states.get(uid)

    # مستخدم
    if txt == "🚶‍♂️ مستخدم":
        user_states[uid] = "awaiting_governorate"
        return await update.message.reply_text("اختار محافظتك:", reply_markup=ReplyKeyboardMarkup([[g] for g in GOVS], True))

    if st == "awaiting_governorate":
        if txt not in GOVS:
            return await update.message.reply_text("❌ اختر من القائمة.")
        user_data[uid] = {"governorate": txt}
        user_states[uid] = "awaiting_area"
        return await update.message.reply_text("اختار الحي:", reply_markup=ReplyKeyboardMarkup([[a] for a in AREAS], True))

    if st == "awaiting_area":
        if txt not in AREAS:
            return await update.message.reply_text("❌ اختر من القائمة.")
        user_data[uid]["area"] = txt
        user_states[uid] = "awaiting_order"
        return await update.message.reply_text("اكتب تفاصيل طلبك:", reply_markup=ReplyKeyboardRemove())

    if st == "awaiting_order":
        order_text = txt
        gov, area = user_data[uid]["governorate"], user_data[uid]["area"]
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("INSERT INTO orders (user_id, governorate, area, text, status) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                        (uid, gov, area, order_text, "قيد الانتظار"))
            oid = cur.fetchone()[0]
            conn.commit()

            # إرسال الطلب للمناديب في نفس المنطقة
            cur.execute("SELECT user_id FROM agents WHERE is_verified=TRUE AND governorate=%s AND area=%s", (gov, area))
            agents = cur.fetchall()
            conn.close()

            for (aid,) in agents:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("📝 عرض", callback_data=f"offer_{oid}")]])
                await context.bot.send_message(chat_id=aid, text=f"طلب جديد من {area}:\n{order_text}", reply_markup=kb)

            await update.message.reply_text("✅ تم تسجيل طلبك بنجاح.")
        except Exception as e:
            logging.error(e)
            await update.message.reply_text("❌ حصل خطأ أثناء تسجيل الطلب.")

        user_states[uid] = None
        user_data[uid] = {}
        return

    # مندوب
    if txt == "🚚 مندوب":
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT is_verified FROM agents WHERE user_id=%s", (uid,))
            row = cur.fetchone()
            conn.close()
            if row:
                return await update.message.reply_text("✅ تم قبولك كمندوب." if row[0] else "⏳ طلبك قيد المراجعة.")
        except Exception as e:
            logging.error(e)
        user_states[uid] = "awaiting_agent_name"
        return await update.message.reply_text("اكتب اسمك الكامل:")

    if st == "awaiting_agent_name":
        user_data[uid] = {"full_name": txt}
        user_states[uid] = "awaiting_agent_governorate"
        return await update.message.reply_text("اختار محافظتك:", reply_markup=ReplyKeyboardMarkup([[g] for g in GOVS], True))

    if st == "awaiting_agent_governorate":
        if txt not in GOVS:
            return await update.message.reply_text("❌ اختر من القائمة.")
        user_data[uid]["governorate"] = txt
        user_states[uid] = "awaiting_agent_area"
        return await update.message.reply_text("اختار الحي:", reply_markup=ReplyKeyboardMarkup([[a] for a in AREAS], True))

    if st == "awaiting_agent_area":
        if txt not in AREAS:
            return await update.message.reply_text("❌ اختر من القائمة.")
        user_data[uid]["area"] = txt
        user_states[uid] = "awaiting_id_photo"
        return await update.message.reply_text("📸 ارفع صورة بطاقتك:")

    await update.message.reply_text("❗ استخدم /start لإعادة البدء.")

# استقبال صورة البطاقة
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if user_states.get(uid) == "awaiting_id_photo":
        try:
            fid = update.message.photo[-1].file_id
            file = await context.bot.get_file(fid)
            url = file.file_path
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                result = cloudinary.uploader.upload(resp.content)
                img_url = result["secure_url"]

            data = user_data[uid]
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("INSERT INTO agents (user_id, full_name, governorate, area, id_photo_url, is_verified) VALUES (%s, %s, %s, %s, %s, FALSE)",
                        (uid, data["full_name"], data["governorate"], data["area"], img_url))
            conn.commit()
            conn.close()
            await update.message.reply_text("✅ تم استلام بياناتك وجاري المراجعة.")
        except Exception as e:
            logging.error(e)
            await update.message.reply_text("❌ فشل في رفع أو حفظ الصورة.")
        user_states[uid] = None
        user_data[uid] = {}

# استقبال العروض من المناديب
async def handle_offer_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    uid = q.from_user.id

    if d.startswith("offer_"):
        oid = int(d.split("_")[1])
        user_data[uid] = {"order_id": oid}
        user_states[uid] = "awaiting_offer_price"
        kb = [[InlineKeyboardButton(p, callback_data=f"price_{p}")] for p in PRICE_OPTS]
        return await q.message.reply_text("اختر السعر:", reply_markup=InlineKeyboardMarkup(kb))

    if d.startswith("price_"):
        pr = d.split("_")[1]
        user_data[uid]["price"] = pr
        user_states[uid] = "awaiting_offer_time"
        kb = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in TIME_OPTS]
        return await q.message.reply_text("اختر الوقت:", reply_markup=InlineKeyboardMarkup(kb))

    if d.startswith("time_"):
        time = d.split("_")[1]
        info = user_data.get(uid, {})
        oid = info["order_id"]
        price = info["price"]
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("INSERT INTO offers (order_id, agent_id, price, estimated_time) VALUES (%s, %s, %s, %s)", (oid, uid, price, time))
            conn.commit()

            # جلب بيانات المستخدم
            cur.execute("SELECT user_id FROM orders WHERE id=%s", (oid,))
            user_row = cur.fetchone()
            if user_row:
                user_id = user_row[0]
                cur.execute("SELECT full_name FROM agents WHERE user_id=%s", (uid,))
                agent_row = cur.fetchone()
                agent_name = agent_row[0] if agent_row else "مندوب"
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ قبول هذا العرض", callback_data=f"accept_offer_{oid}_{uid}")]])
                msg = f"📝 عرض جديد:\n👤 المندوب: {agent_name}\n💰 السعر: {price}\n⏱️ الوقت: {time}"
                await context.bot.send_message(chat_id=user_id, text=msg, reply_markup=kb)
            conn.close()

            await q.message.reply_text("✅ تم إرسال العرض.")
        except Exception as e:
            logging.error(e)
            await q.message.reply_text("❌ فشل في إرسال العرض.")

        user_states[uid] = None
        user_data[uid] = {}

# قبول المستخدم للعرض
async def handle_accept_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data  # accept_offer_3_123456
    _, _, oid_str, agent_id_str = data.split("_")
    oid = int(oid_str)
    agent_id = int(agent_id_str)

    try:
        conn = get_conn()
        cur = conn.cursor()

        # تحديث الطلب
        cur.execute("UPDATE orders SET status='قيد التنفيذ' WHERE id=%s", (oid,))
        cur.execute("DELETE FROM offers WHERE order_id=%s AND agent_id<>%s", (oid, agent_id))
        conn.commit()
        conn.close()

        await q.message.reply_text("✅ تم قبول هذا العرض.")
        await context.bot.send_message(chat_id=agent_id, text=f"🎉 تم اختيارك لتنفيذ الطلب رقم {oid}.")
    except Exception as e:
        logging.error(e)
        await q.message.reply_text("❌ حصل خطأ أثناء قبول العرض.")

# تشغيل البوت
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_role))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_offer_button, pattern="^(offer_|price_|time_)"))
    app.add_handler(CallbackQueryHandler(handle_accept_offer, pattern="^accept_offer_"))
    app.run_polling()
