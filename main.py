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
            # جلب المناديب المفعلين في نفس المنطقة
            cur.execute("SELECT user_id FROM agents WHERE is_verified=TRUE AND governorate=%s AND area=%s", (gov, area))
            agents = cur.fetchall()
            conn.close()
            for (aid,) in agents:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("📝 إرسال عرض", callback_data=f"offer_{oid}")]])
                await context.bot.send_message(chat_id=aid, text=f"طلب جديد من {area}:\n{ text }", reply_markup=kb)
            await update.message.reply_text("✅ تم إرسال الطلب، المناديب سيقدمون عروضهم قريباً.")
        except Exception as e:
            logging.error(e)
            await update.message.reply_text("❌ حصل خطأ أثناء إرسال الطلب.")
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
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("INSERT INTO agents (user_id, full_name, governorate, area, id_photo_url, is_verified) VALUES (%s,%s,%s,%s,%s,FALSE)",
                (uid, d["full_name"], d["governorate"], d["area"], pu))
            conn.commit()
            conn.close()
            await update.message.reply_text("✅ تم الاستلام، في انتظار مراجعة الإدارة.")
        except Exception as e:
            logging.error(e)
            await update.message.reply_text("❌ فشل في الرفع أو الحفظ.")
        user_states[uid] = None
        user_data[uid] = {}

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
        await q.message.reply_text("اختار السعر:", reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("price_"):
        pr = d.split("_")[1]
        user_data[uid]["price"] = pr
        user_states[uid] = "awaiting_offer_time"
        kb = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in TIME_OPTS]
        await q.message.reply_text("اختار الزمن:", reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("time_"):
        tm = d.split("_")[1]
        info = user_data.get(uid, {})
        oid = info.get("order_id")
        pr = info.get("price")
        try:
            conn = get_conn()
            cur = conn.cursor()
            # تحقق إذا المندوب قدم عرض سابق لنفس الطلب، إذا نعم حدثه وإلا أضفه
            cur.execute("SELECT id FROM offers WHERE order_id=%s AND agent_id=%s", (oid, uid))
            existing = cur.fetchone()
            if existing:
                cur.execute("UPDATE offers SET price=%s, estimated_time=%s WHERE id=%s", (pr, tm, existing[0]))
            else:
                cur.execute("INSERT INTO offers (order_id, agent_id, price, estimated_time) VALUES (%s,%s,%s,%s)",
                            (oid, uid, pr, tm))
            conn.commit()
            conn.close()
            await q.message.reply_text("✅ تم إرسال العرض.")
        except Exception as e:
            logging.error(e)
            await q.message.reply_text("❌ فشل في إرسال العرض.")
        user_states[uid] = None
        user_data[uid] = {}
async def send_offers_to_user(context, user_id, order_id):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT offers.id, agents.full_name, offers.price, offers.estimated_time, offers.agent_id
            FROM offers
            JOIN agents ON offers.agent_id = agents.user_id
            WHERE offers.order_id = %s
        """, (order_id,))
        offers = cur.fetchall()
        conn.close()

        if not offers:
            await context.bot.send_message(chat_id=user_id, text="لا توجد عروض لهذا الطلب حتى الآن.")
            return

        buttons = []
        for offer_id, agent_name, price, est_time, agent_id in offers:
            offer_text = f"العرض من {agent_name}\nالسعر: {price}\nالوقت المتوقع: {est_time}"
            buttons.append([
                InlineKeyboardButton("✅ قبول", callback_data=f"acceptoffer_{offer_id}_{agent_id}"),
                InlineKeyboardButton("❌ رفض", callback_data=f"rejectoffer_{offer_id}_{agent_id}")
            ])

        await context.bot.send_message(chat_id=user_id, text="العروض المتاحة:\nاختر العرض المناسب لك:", reply_markup=InlineKeyboardMarkup(buttons))

    except Exception as e:
        logging.error(e)
        await context.bot.send_message(chat_id=user_id, text="❌ حدث خطأ أثناء جلب العروض.")

async def handle_accept_reject_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    parts = data.split("_")

    if parts[0] == "acceptoffer":
        offer_id = int(parts[1])
        agent_id = int(parts[2])

        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT order_id FROM offers WHERE id=%s", (offer_id,))
            order_id = cur.fetchone()[0]

            # حدث حالة الطلب وحط المندوب المختار
            cur.execute("UPDATE orders SET status='قيد التنفيذ', selected_agent_id=%s WHERE id=%s", (agent_id, order_id))
            conn.commit()

            # حذف العروض الأخرى
            cur.execute("DELETE FROM offers WHERE order_id=%s AND id!=%s", (order_id, offer_id))
            conn.commit()

            # جلب بيانات المستخدم لإرسالها للمندوب
            cur.execute("SELECT user_id, governorate, area, address, phone FROM orders WHERE id=%s", (order_id,))
            user_info = cur.fetchone()
            conn.close()

            user_id, gov, area, address, phone = user_info

            # إعلام المندوب
            msg_agent = (
                f"🎉 تم اختيارك لتنفيذ الطلب رقم {order_id}.\n\n"
                f"معلومات المستخدم:\n🏙️ {gov} - {area}\n📍 العنوان: {address}\n📞 الهاتف: {phone}"
            )
            await context.bot.send_message(chat_id=agent_id, text=msg_agent)

            # إعلام المستخدم
            await q.message.edit_text("✅ شكراً! تم اختيار المندوب وسيبدأ التنفيذ قريباً.")

            # اختياري: إعلام باقي المناديب أن عروضهم مرفوضة

        except Exception as e:
            logging.error(e)
            await q.message.reply_text("❌ حدث خطأ أثناء قبول العرض.")

    elif parts[0] == "rejectoffer":
        offer_id = int(parts[1])
        agent_id = int(parts[2])
        await q.message.edit_text("❌ تم رفض العرض. يمكنك انتظار عروض أخرى.")

# مثال مبسط على تأكيد التوصيل من المندوب
async def confirm_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        conn = get_conn()
        cur = conn.cursor()
        # تحقق من وجود طلب قيد التنفيذ للمندوب
        cur.execute("SELECT id FROM orders WHERE selected_agent_id=%s AND status='قيد التنفيذ'", (uid,))
        row = cur.fetchone()
        if not row:
            await update.message.reply_text("ليس لديك طلب قيد التنفيذ.")
            conn.close()
            return
        order_id = row[0]
        # تحديث حالة الطلب بعد التوصيل
        cur.execute("UPDATE orders SET status='تم التوصيل' WHERE id=%s", (order_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text("✅ تم تأكيد التوصيل. يرجى من المستخدم إرسال تقييمه.")
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ حدث خطأ أثناء تأكيد التوصيل.")

# استقبال تقييم المستخدم بعد التوصيل
async def receive_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    rating = update.message.text
    try:
        rating_val = int(rating)
        if rating_val < 1 or rating_val > 5:
            return await update.message.reply_text("يرجى إرسال تقييم بين 1 و 5 فقط.")

        conn = get_conn()
        cur = conn.cursor()
        # جلب الطلبات التي تم توصيلها ولم يتم تقييمها بعد من قبل المستخدم
        cur.execute("SELECT id FROM orders WHERE user_id=%s AND status='تم التوصيل' AND rating IS NULL", (uid,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return await update.message.reply_text("ليس لديك طلبات بحاجة لتقييم.")

        order_id = row[0]
        cur.execute("UPDATE orders SET rating=%s WHERE id=%s", (rating_val, order_id))
        conn.commit()
        conn.close()
        await update.message.reply_text("✅ تم استلام تقييمك، شكراً لك!")

    except ValueError:
        await update.message.reply_text("يرجى إرسال رقم تقييم صحيح (1 إلى 5).")
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ حدث خطأ أثناء إرسال التقييم.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_role))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    app.add_handler(CallbackQueryHandler(handle_offer_button, pattern=r"^(offer|price|time)_"))
    app.add_handler(CallbackQueryHandler(handle_accept_reject_offer, pattern=r"^(acceptoffer|rejectoffer)_"))

    # أمر لتأكيد التوصيل من المندوب
    app.add_handler(CommandHandler("delivered", confirm_delivery))
    # استقبال تقييم من المستخدم (افتراضياً، أي رسالة نصية بين 1 و5)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_rating))

    app.run_polling()
