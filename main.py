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

    # بداية تسجيل بيانات المستخدم
    if txt == "🚶‍♂️ مستخدم":
        user_states[uid] = "awaiting_governorate"
        return await update.message.reply_text("اختار محافظتك:", reply_markup=ReplyKeyboardMarkup([[g] for g in GOVS], True))

    st = user_states.get(uid)

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

    # تسجيل الطلب وارساله للمناديب
    if st == "awaiting_order":
        gov = user_data[uid]["governorate"]
        area = user_data[uid]["area"]
        address = user_data[uid]["address"]
        phone = user_data[uid]["phone"]
        text = txt
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""INSERT INTO orders 
                (user_id, governorate, area, address, phone, text, status) 
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (uid, gov, area, address, phone, text, "قيد الانتظار"))
            oid = cur.fetchone()[0]
            conn.commit()
            cur.execute("SELECT user_id FROM agents WHERE is_verified=TRUE AND governorate=%s AND area=%s", (gov, area))
            agents = cur.fetchall()
            conn.close()
            for (aid,) in agents:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("📝 عرض", callback_data=f"offer_{oid}_{uid}")]])
                await context.bot.send_message(chat_id=aid, text=f"طلب جديد من {area}:\n{text}", reply_markup=kb)
            await update.message.reply_text("✅ تم إرسال الطلب وسيتم التواصل معك قريباً.")
        except Exception as e:
            logging.error(e)
            await update.message.reply_text("❌ حصل خطأ أثناء إرسال الطلب.")
        user_states[uid] = None
        user_data[uid] = {}
        return

    # تسجيل بيانات المندوب
    if txt == "🚚 مندوب":
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT is_verified FROM agents WHERE user_id=%s", (uid,))
            row = cur.fetchone()
            conn.close()
            if row:
                if row[0]:
                    return await update.message.reply_text("✅ مفعل وتقدر تستقبل الطلبات.")
                else:
                    return await update.message.reply_text("⏳ طلبك تحت المراجعة.")
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
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""INSERT INTO agents 
                (user_id, full_name, governorate, area, id_photo_url, is_verified) 
                VALUES (%s,%s,%s,%s,%s,FALSE)""",
                (uid, d["full_name"], d["governorate"], d["area"], pu))
            conn.commit()
            conn.close()
            await update.message.reply_text("✅ تم الاستلام، في انتظار مراجعة الإدارة.")
        except Exception as e:
            logging.error(e)
            await update.message.reply_text("❌ فشل في الرفع أو الحفظ.")
        user_states[uid] = None
        user_data[uid] = {}

# المندوب يرسل العرض
async def handle_offer_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    uid = q.from_user.id

    if d.startswith("offer_"):
        parts = d.split("_")
        if len(parts) != 3:
            return await q.message.reply_text("❌ خطأ في بيانات العرض.")
        oid = int(parts[1])
        user_id = int(parts[2])
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
        pr = info.get("price")
        user_id = info.get("user_id")
        if not oid or not pr or not user_id:
            return await q.message.reply_text("❌ بيانات ناقصة لإرسال العرض.")
        try:
            conn = get_conn()
            cur = conn.cursor()
            # إضافة العرض
            cur.execute("INSERT INTO offers (order_id, agent_id, price, estimated_time) VALUES (%s,%s,%s,%s)",
                        (oid, uid, pr, tm))
            conn.commit()
            conn.close()

            # إرسال عرض للمستخدم مع أزرار قبول ورفض العرض
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ قبول", callback_data=f"accept_offer_{oid}_{uid}"),
                 InlineKeyboardButton("❌ رفض", callback_data=f"reject_offer_{oid}_{uid}")]
            ])
            await context.bot.send_message(chat_id=user_id,
                text=f"📢 وصل عرض جديد لطلبك #{oid}:\nالسعر: {pr}\nالوقت المتوقع: {tm}\nهل توافق؟",
                reply_markup=kb)

            await q.message.reply_text("✅ تم إرسال العرض.")
        except Exception as e:
            logging.error(e)
            await q.message.reply_text("❌ فشل في إرسال العرض.")
        user_states[uid] = None
        user_data[uid] = {}

# المستخدم يرد على العرض (قبول أو رفض)
async def handle_offer_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data

    parts = d.split("_")
    if len(parts) != 4:
        return await q.message.reply_text("❌ خطأ في بيانات الرد.")
    action, _, oid_str, aid_str = parts
    oid = int(oid_str)
    aid = int(aid_str)

    try:
        conn = get_conn()
        cur = conn.cursor()
        if action == "accept":
            # تحديث حالة الطلب واختيار المندوب
            cur.execute("UPDATE orders SET status='قيد التنفيذ', selected_agent_id=%s WHERE id=%s", (aid, oid))
            conn.commit()

            # حذف عروض أخرى لنفس الطلب
            cur.execute("DELETE FROM offers WHERE order_id=%s AND agent_id!=%s", (oid, aid))
            conn.commit()
            conn.close()

            # إرسال إشعار للمندوب الفائز مع بيانات المستخدم
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT governorate, area, address, phone, text, user_id FROM orders WHERE id=%s", (oid,))
            order = cur.fetchone()
            conn.close()
            gov, area, address, phone, text, user_id = order
            msg = (
                f"🎉 تم اختيارك لتنفيذ الطلب رقم {oid}.\n\n"
                f"بيانات المستخدم:\n"
                f"المحافظة: {gov}\n"
                f"الحي: {area}\n"
                f"العنوان: {address}\n"
                f"رقم التليفون: {phone}\n"
                f"تفاصيل الطلب: {text}"
            )
            await context.bot.send_message(chat_id=aid, text=msg)

            # إعلام المستخدم بنجاح الاختيار
            await context.bot.send_message(chat_id=user_id, text=f"✅ تم اختيار المندوب بنجاح، تواصل مع المندوب لاستلام طلبك.")

        elif action == "reject":
            # حذف العرض المرفوض
            cur.execute("DELETE FROM offers WHERE order_id=%s AND agent_id=%s", (oid, aid))
            conn.commit()
            conn.close()
            await context.bot.send_message(chat_id=q.from_user.id, text="❌ تم رفض العرض.")
    except Exception as e:
        logging.error(e)
        await q.message.reply_text("❌ حصل خطأ في معالجة رد العرض.")

# المندوب يضغط "تم التوصيل"
async def handle_delivered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    if text == "تم التوصيل":
        try:
            conn = get_conn()
            cur = conn.cursor()
            # البحث عن الطلب الجاري للمندوب
            cur.execute("SELECT id, user_id FROM orders WHERE selected_agent_id=%s AND status='قيد التنفيذ'", (uid,))
            order = cur.fetchone()
            if not order:
                await update.message.reply_text("❌ لا يوجد طلبات معلقة لك حالياً.")
                conn.close()
                return
            oid, user_id = order

            # تحديث حالة الطلب إلى "تم التوصيل"
            cur.execute("UPDATE orders SET status='تم التوصيل' WHERE id=%s", (oid,))
            conn.commit()
            conn.close()

            # إرسال رسالة للمستخدم لتقييم الخدمة
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐️ 1", callback_data=f"rate_{oid}_1"),
                 InlineKeyboardButton("⭐️ 2", callback_data=f"rate_{oid}_2"),
                 InlineKeyboardButton("⭐️ 3", callback_data=f"rate_{oid}_3"),
                 InlineKeyboardButton("⭐️ 4", callback_data=f"rate_{oid}_4"),
                 InlineKeyboardButton("⭐️ 5", callback_data=f"rate_{oid}_5")]
            ])
            await context.bot.send_message(chat_id=user_id,
                text=f"🔔 تم توصيل طلبك رقم {oid}. من فضلك قيم الخدمة بنجمة واحدة على الأقل:",
                reply_markup=kb)

            await update.message.reply_text("✅ تم تأكيد التوصيل، الرجاء انتظار تقييم المستخدم.")

        except Exception as e:
            logging.error(e)
            await update.message.reply_text("❌ حصل خطأ أثناء تحديث حالة التوصيل.")

# المستخدم يرسل تقييمه
async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data

    parts = d.split("_")
    if len(parts) != 3:
        return await q.message.reply_text("❌ خطأ في بيانات التقييم.")
    _, oid_str, rating_str = parts
    oid = int(oid_str)
    rating = int(rating_str)
    uid = q.from_user.id

    try:
        conn = get_conn()
        cur = conn.cursor()
        # الحصول على المندوب المختار للطلب
        cur.execute("SELECT selected_agent_id FROM orders WHERE id=%s", (oid,))
        row = cur.fetchone()
        if not row:
            await q.message.reply_text("❌ الطلب غير موجود.")
            conn.close()
            return
        agent_id = row[0]

        # حفظ التقييم
        cur.execute("INSERT INTO ratings (order_id, agent_id, rating, user_id) VALUES (%s,%s,%s,%s)",
                    (oid, agent_id, rating, uid))
        conn.commit()
        conn.close()

        # إعلام المستخدم بنجاح التقييم
        await q.message.reply_text("✅ شكراً لتقييمك!")

    except Exception as e:
        logging.error(e)
        await q.message.reply_text("❌ حصل خطأ أثناء حفظ التقييم.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_role))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_offer_button, pattern="^(offer_|price_|time_).+"))
    app.add_handler(CallbackQueryHandler(handle_offer_response, pattern="^(accept_offer_|reject_offer_).+"))
    app.add_handler(MessageHandler(filters.Regex("^تم التوصيل$"), handle_delivered))
    app.add_handler(CallbackQueryHandler(handle_rating, pattern="^rate_"))

    app.run_polling()
