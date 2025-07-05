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

user_states, user_data = {}, {}
GOVS = ["الغربية"]
AREAS = ["أول طنطا", "ثان طنطا", "حي السيالة", "حي الصاغة", "حي سعيد", "شارع البحر", "شارع الحلو", "محطة القطار", "موقف الجلاء"]
PRICE_OPTS = ["10 جنيه", "15 جنيه", "20 جنيه"]
TIME_OPTS = ["10 دقايق", "15 دقيقه", "30 دقيقه"]
RATING_OPTS = [("⭐", 1), ("⭐⭐", 2), ("⭐⭐⭐", 3), ("⭐⭐⭐⭐", 4), ("⭐⭐⭐⭐⭐", 5)]

def get_conn():
    return psycopg2.connect(DATABASE_URL)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    keyboard = [[KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]]
    await update.message.reply_text("أهلاً بيك! اختار دورك:", reply_markup=ReplyKeyboardMarkup(keyboard, True))
    user_states[uid] = None

async def handle_user_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        user_states[uid] = "awaiting_address"
        return await update.message.reply_text("اكتب عنوانك بالتفصيل:", reply_markup=ReplyKeyboardRemove())

    if st == "awaiting_address":
        user_data[uid]["address"] = txt
        user_states[uid] = "awaiting_phone"
        return await update.message.reply_text("اكتب رقم تليفونك:")

    if st == "awaiting_phone":
        user_data[uid]["phone"] = txt
        user_states[uid] = "awaiting_order"
        return await update.message.reply_text("اكتب تفاصيل طلبك:")

    if st == "awaiting_order":
        gov = user_data[uid]["governorate"]
        area = user_data[uid]["area"]
        address = user_data[uid]["address"]
        phone = user_data[uid]["phone"]
        text = txt
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO orders (user_id, governorate, area, address, phone, text, status) 
                VALUES (%s,%s,%s,%s,%s,%s,'قيد الانتظار') RETURNING id
            """, (uid, gov, area, address, phone, text))
            oid = cur.fetchone()[0]
            conn.commit()

            cur.execute("SELECT user_id FROM agents WHERE is_verified=TRUE AND governorate=%s AND area=%s", (gov, area))
            agents = cur.fetchall()
            conn.close()
            for (aid,) in agents:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("📝 عرض", callback_data=f"offer_{oid}_{uid}")]])
                await context.bot.send_message(chat_id=aid, text=f"طلب جديد من {area}:\n{text}", reply_markup=kb)
            await update.message.reply_text("✅ تم إرسال الطلب، استنى العروض.")
        except Exception as e:
            logging.error(e)
            await update.message.reply_text("❌ حصل خطأ أثناء إرسال الطلب.")
        user_states[uid] = None
        user_data[uid] = {}
        return

    if txt == "🚚 مندوب":
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute("SELECT is_verified FROM agents WHERE user_id=%s", (uid,))
            row = cur.fetchone(); conn.close()
            if row:
                return await update.message.reply_text("✅ مفعل وتقدر تستقبل الطلبات." if row[0] else "⏳ طلبك تحت المراجعة.")
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

    await update.message.reply_text("❗ استخدم /start للبدء من جديد.")
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if user_states.get(uid) == "awaiting_id_photo":
        fid = update.message.photo[-1].file_id
        try:
            file = await context.bot.get_file(fid)
            url = file.file_path
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                result = cloudinary.uploader.upload(resp.content)
                pu = result["secure_url"]

            d = user_data[uid]
            conn = get_conn(); cur = conn.cursor()
            cur.execute("INSERT INTO agents (user_id, full_name, governorate, area, id_photo_url, is_verified) VALUES (%s,%s,%s,%s,%s,FALSE)",
                (uid, d["full_name"], d["governorate"], d["area"], pu))
            conn.commit(); conn.close()
            await update.message.reply_text("✅ تم الاستلام، في انتظار مراجعة الإدارة.")
        except Exception as e:
            logging.error(e)
            await update.message.reply_text("❌ فشل في الرفع أو الحفظ.")
        user_states[uid] = None; user_data[uid] = {}

async def handle_offer_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    uid = q.from_user.id

    if d.startswith("offer_"):
        _, oid, user_id = d.split("_")
        user_data[uid] = {"order_id": oid, "user_id": user_id}
        user_states[uid] = "awaiting_offer_price"
        kb = [[InlineKeyboardButton(p, callback_data=f"price_{p}")] for p in PRICE_OPTS]
        return await q.message.reply_text("اختار السعر:", reply_markup=InlineKeyboardMarkup(kb))

    if d.startswith("price_"):
        pr = d.split("_")[1]
        user_data[uid]["price"] = pr
        user_states[uid] = "awaiting_offer_time"
        kb = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in TIME_OPTS]
        return await q.message.reply_text("اختار الزمن:", reply_markup=InlineKeyboardMarkup(kb))

    if d.startswith("time_"):
        tm = d.split("_")[1]
        info = user_data.get(uid, {})
        oid = info.get("order_id")
        usr = info.get("user_id")
        pr = info.get("price")
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("INSERT INTO offers (order_id, agent_id, price, estimated_time) VALUES (%s,%s,%s,%s)",
                        (oid, uid, pr, tm))
            conn.commit(); conn.close()
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ قبول", callback_data=f"accept_{oid}_{uid}")],
                [InlineKeyboardButton("❌ رفض", callback_data=f"reject_{oid}_{uid}")]
            ])
            await context.bot.send_message(chat_id=int(usr), text=f"📬 عرض جديد على طلبك:\n💸 السعر: {pr}\n🕒 الزمن: {tm}", reply_markup=kb)
            await q.message.reply_text("✅ تم إرسال العرض.")
        except Exception as e:
            logging.error(e)
            await q.message.reply_text("❌ فشل في إرسال العرض.")
        user_states[uid] = None
        user_data[uid] = {}

async def handle_offer_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    uid = q.from_user.id

    if d.startswith("accept_"):
        _, oid, aid = d.split("_")
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("UPDATE orders SET status='قيد التنفيذ', selected_agent_id=%s WHERE id=%s", (aid, oid))
            cur.execute("SELECT address, phone FROM orders WHERE id=%s", (oid,))
            address, phone = cur.fetchone()
            conn.commit(); conn.close()

            await context.bot.send_message(chat_id=int(aid), text=f"🎉 تم اختيارك لتنفيذ الطلب رقم {oid}.\n📍 العنوان: {address}\n📞 التليفون: {phone}")

            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚚 تم التوصيل", callback_data=f"delivered_{oid}_{aid}")]])
            await q.message.reply_text("✅ تم اختيار العرض بنجاح.", reply_markup=kb)
        except Exception as e:
            logging.error(e)
            await q.message.reply_text("❌ حصل خطأ أثناء قبول العرض.")

    elif d.startswith("reject_"):
        await q.message.reply_text("❌ تم رفض العرض.")

    elif d.startswith("delivered_"):
        _, oid, aid = d.split("_")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(txt, callback_data=f"rate_{oid}_{aid}_{val}")] for txt, val in RATING_OPTS])
        await q.message.reply_text("🙏 قيّم تجربتك مع المندوب:", reply_markup=kb)

    elif d.startswith("rate_"):
        _, oid, aid, rate = d.split("_")
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("UPDATE orders SET status='تم التوصيل' WHERE id=%s", (oid,))
            cur.execute("INSERT INTO ratings (order_id, agent_id, rating) VALUES (%s,%s,%s)", (oid, aid, rate))
            conn.commit(); conn.close()
            await q.message.reply_text("✅ شكراً على تقييمك!")
            await context.bot.send_message(chat_id=int(aid), text="🌟 تم تقييمك على الطلب الأخير.")
        except Exception as e:
            logging.error(e)
            await q.message.reply_text("❌ حصل خطأ أثناء حفظ التقييم.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_role))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_offer_button, pattern="^(offer_|price_|time_)"))
    app.add_handler(CallbackQueryHandler(handle_offer_response, pattern="^(accept_|reject_|delivered_|rate_)"))
    app.run_polling()
