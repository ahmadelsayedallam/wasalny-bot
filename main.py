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

# إعداد المتغيرات
TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# حالة المستخدم
user_states, user_data = {}, {}
GOVS = ["الغربية"]
AREAS = ["أول طنطا", "ثان طنطا", "حي السيالة", "حي الصاغة", "حي سعيد", "شارع البحر", "شارع الحلو", "محطة القطار", "موقف الجلاء"]
PRICE_OPTS = ["10 جنيه", "15 جنيه", "20 جنيه"]
TIME_OPTS = ["10 دقايق", "15 دقيقه", "30 دقيقه"]

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

    if txt == "🚶‍♂️ مستخدم":
        user_states[uid] = "awaiting_governorate"
        return await update.message.reply_text("اختار محافظتك:", reply_markup=ReplyKeyboardMarkup([[g] for g in GOVS], True))

    st = user_states.get(uid)
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
            cur.execute("INSERT INTO orders (user_id, governorate, area, address, phone, text, status) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (uid, gov, area, address, phone, text, "قيد الانتظار"))
            oid = cur.fetchone()[0]
            conn.commit()
            cur.execute("SELECT user_id FROM agents WHERE is_verified=TRUE AND governorate=%s AND area=%s", (gov, area))
            agents = cur.fetchall()
            conn.close()
            for (aid,) in agents:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("📝 عرض", callback_data=f"offer_{oid}_{uid}")]])
                await context.bot.send_message(chat_id=aid, text=f"طلب جديد من {area}:\n{ text }", reply_markup=kb)
            await update.message.reply_text("✅ تم إرسال الطلب وسيتم التواصل معك قريباً.")
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
    parts = d.split("_")

    if parts[0] == "offer":
        oid = int(parts[1])
        # سجل الطلب الحالي في user_data مع المفتاح (uid, oid)
        user_data[(uid, oid)] = {}
        # اعرض له اختيار السعر
        kb = [[InlineKeyboardButton(p, callback_data=f"price_{p}_{oid}_{uid}")] for p in PRICE_OPTS]
        await q.message.reply_text("اختار السعر:", reply_markup=InlineKeyboardMarkup(kb))

    elif parts[0] == "price":
        price = parts[1]
        oid = int(parts[2])
        agent_id = int(parts[3])
        user_data[(uid, oid)]["price"] = price
        # عرض اختيار الوقت
        kb = [[InlineKeyboardButton(t, callback_data=f"time_{t}_{oid}_{uid}")] for t in TIME_OPTS]
        await q.message.reply_text("اختار الوقت:", reply_markup=InlineKeyboardMarkup(kb))

    elif parts[0] == "time":
        time_choice = parts[1]
        oid = int(parts[2])
        agent_id = int(parts[3])
        price = user_data.get((uid, oid), {}).get("price")
        if not price:
            await q.message.reply_text("❌ لم يتم اختيار السعر من قبل.")
            return
        # خزن العرض في DB
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO offers (order_id, agent_id, price, estimated_time) VALUES (%s, %s, %s, %s)",
                (oid, uid, price, time_choice)
            )
            conn.commit()
            conn.close()
            await q.message.reply_text("✅ تم إرسال العرض.")
        except Exception as e:
            logging.error(e)
            await q.message.reply_text("❌ فشل في إرسال العرض.")
        # نظف الحالة
        user_data.pop((uid, oid), None)

# إضافة باقي الدوال (مثال: قبول العرض من المستخدم، إرسال بيانات للمندوب، تحديث حالة الطلب، إشعار التوصيل، استقبال تقييم المستخدم)

async def handle_user_accept_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    parts = d.split("_")
    if parts[0] != "acceptoffer":
        return
    oid = int(parts[1])
    aid = int(parts[2])

    try:
        conn = get_conn()
        cur = conn.cursor()
        # تحديث حالة الطلب مع حفظ المندوب المختار
        cur.execute("UPDATE orders SET status='قيد التنفيذ', selected_agent_id=%s WHERE id=%s", (aid, oid))
        conn.commit()

        # جلب بيانات المستخدم ليرسلها للمندوب
        cur.execute("SELECT user_id, governorate, area, address, phone FROM orders WHERE id=%s", (oid,))
        user_info = cur.fetchone()
        conn.close()

        # إرسال رسالة للمندوب
        user_id, gov, area, address, phone = user_info
        msg = f"🎉 تم اختيارك لتنفيذ الطلب رقم {oid}.\n\nمعلومات المستخدم:\n🏙️ {gov} - {area}\n📍 العنوان: {address}\n📞 الهاتف: {phone}"
        await context.bot.send_message(chat_id=aid, text=msg)

        # إعلام المستخدم بنجاح الاختيار
        await q.message.edit_text("✅ شكراً! تم اختيار المندوب وسيبدأ التنفيذ قريباً.")

        # إعلام باقي المناديب برفض العرض (يمكن إضافة ذلك لاحقاً)

    except Exception as e:
        logging.error(e)
        await q.message.reply_text("❌ حدث خطأ أثناء قبول العرض.")

async def mark_order_delivered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        conn = get_conn()
        cur = conn.cursor()
        # تحديث حالة الطلب إلى "تم التوصيل"
        cur.execute("UPDATE orders SET status='تم التوصيل' WHERE selected_agent_id=%s AND status='قيد التنفيذ'", (uid,))
        conn.commit()
        conn.close()
        await update.message.reply_text("🎉 تم تحديث حالة الطلب إلى تم التوصيل. من فضلك قم بتقييم الخدمة باستخدام /rate")
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ حدث خطأ أثناء تحديث حالة الطلب.")

async def rate_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = context.args
    if not args or not args[0].isdigit():
        return await update.message.reply_text("استخدم الأمر بهذا الشكل:\n/rate 5\nحيث 5 هو التقييم من 1 إلى 5")

    rating = int(args[0])
    if rating < 1 or rating > 5:
        return await update.message.reply_text("التقييم يجب أن يكون بين 1 و 5.")

    try:
        conn = get_conn()
        cur = conn.cursor()
        # تحديث تقييم الطلب الذي تم توصيله للمندوب
        cur.execute("""
            UPDATE orders SET rating=%s WHERE user_id=%s AND status='تم التوصيل' AND rating IS NULL
        """, (rating, uid))
        conn.commit()
        conn.close()
        await update.message.reply_text("✅ شكراً لتقييمك!")
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ حدث خطأ أثناء حفظ التقييم.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_role))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_offer_button))

    # إضافة أمر قبول العرض من المستخدم (مثلاً أزرار قبول/رفض في مكان عرض العروض)
    app.add_handler(CallbackQueryHandler(handle_user_accept_offer, pattern=r"^acceptoffer_\d+_\d+$"))

    # أمر المندوب لتأكيد التوصيل
    app.add_handler(CommandHandler("delivered", mark_order_delivered))

    # أمر المستخدم لإرسال تقييم
    app.add_handler(CommandHandler("rate", rate_order))

    app.run_polling()
