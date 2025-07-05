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
            # جلب كل المناديب في المحافظة والحي
            cur.execute("SELECT user_id FROM agents WHERE is_verified=TRUE AND governorate=%s AND area=%s", (gov, area))
            agents = cur.fetchall()
            conn.close()
            for (aid,) in agents:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("📝 عرض", callback_data=f"offer_{oid}_{uid}")]])
                await context.bot.send_message(chat_id=aid, text=f"طلب جديد من {area}:\n{address}\n{phone}\n{txt}", reply_markup=kb)
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
        user_states[uid] = None
        user_data[uid] = {}


async def handle_offer_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    uid = q.from_user.id

    if d.startswith("offer_"):
        parts = d.split("_")
        if len(parts) != 3:
            await q.message.reply_text("❌ خطأ في البيانات.")
            return
        _, oid, order_user_id = parts
        oid = int(oid)
        order_user_id = int(order_user_id)

        user_data[uid] = {"order_id": oid, "order_user_id": order_user_id}
        user_states[uid] = "awaiting_offer_price"
        kb = [[InlineKeyboardButton(p, callback_data=f"price_{p}")] for p in PRICE_OPTS]
        return await q.message.reply_text("اختار السعر:", reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("price_"):
        pr = d.split("_")[1]
        user_data[uid]["price"] = pr
        user_states[uid] = "awaiting_offer_time"
        kb = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in TIME_OPTS]
        return await q.message.reply_text("اختار الزمن:", reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("time_"):
        tm = d.split("_")[1]
        info = user_data.get(uid, {})
        oid = info.get("order_id")
        pr = info.get("price")
        order_user_id = info.get("order_user_id")

        try:
            conn = get_conn()
            cur = conn.cursor()

            cur.execute("SELECT id FROM offers WHERE order_id=%s AND agent_id=%s", (oid, uid))
            existing = cur.fetchone()
            if existing:
                cur.execute("UPDATE offers SET price=%s, estimated_time=%s WHERE id=%s", (pr, tm, existing[0]))
            else:
                cur.execute("INSERT INTO offers (order_id, agent_id, price, estimated_time) VALUES (%s,%s,%s,%s)",
                            (oid, uid, pr, tm))
            conn.commit()

            # أرسل للمستخدم عروض محدثة بعد إضافة هذا العرض
            await send_offers_to_user(context, user_id=order_user_id, order_id=oid)

            conn.close()
            await q.message.reply_text("✅ تم إرسال العرض.")
        except Exception as e:
            logging.error(e)
            await q.message.reply_text("❌ فشل في إرسال العرض.")
        user_states[uid] = None
        user_data[uid] = {}

# دالة لإرسال عروض المناديب للمستخدم ليختار
async def send_offers_to_user(context, user_id, order_id):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT agents.user_id, agents.full_name, offers.price, offers.estimated_time
            FROM offers
            JOIN agents ON offers.agent_id = agents.user_id
            WHERE offers.order_id = %s
        """, (order_id,))
        offers = cur.fetchall()
        conn.close()

        if not offers:
            await context.bot.send_message(chat_id=user_id, text="لا يوجد عروض حتى الآن.")
            return

        buttons = []
        for aid, name, price, time_est in offers:
            text = f"{name} - السعر: {price} - الوقت المتوقع: {time_est}"
            buttons.append([InlineKeyboardButton(text, callback_data=f"selectoffer_{order_id}_{aid}")])

        kb = InlineKeyboardMarkup(buttons)
        await context.bot.send_message(chat_id=user_id, text="وصلتك عروض جديدة. اختر العرض المناسب لك:", reply_markup=kb)
    except Exception as e:
        logging.error(e)

# دالة للتعامل مع قبول العرض من المستخدم
async def handle_offer_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    if data.startswith("selectoffer_"):
        try:
            _, order_id_str, agent_id_str = data.split("_")
            order_id = int(order_id_str)
            agent_id = int(agent_id_str)

            conn = get_conn()
            cur = conn.cursor()

            # تحديث حالة الطلب والمنفذ المختار
            cur.execute("UPDATE orders SET status='قيد التنفيذ', selected_agent_id=%s WHERE id=%s", (agent_id, order_id))

            # جلب بيانات المستخدم صاحب الطلب
            cur.execute("SELECT user_id, governorate, area, address, phone FROM orders WHERE id=%s", (order_id,))
            row = cur.fetchone()
            conn.commit()
            conn.close()

            user_id = row[0]
            gov = row[1]
            area = row[2]
            address = row[3]
            phone = row[4]

            # إعلام المندوب
            await context.bot.send_message(chat_id=agent_id, text=f"🎉 تم اختيارك لتنفيذ الطلب رقم {order_id}.\n"
                                                                  f"بيانات المستخدم:\nالمحافظة: {gov}\nالحي: {area}\nالعنوان: {address}\nرقم التليفون: {phone}")

            # إعلام المستخدم
            await context.bot.send_message(chat_id=user_id, text=f"✅ تم اختيار المندوب لتنفيذ طلبك رقم {order_id}.\n"
                                                                f"سيتم التواصل معك قريباً.")

        except Exception as e:
            logging.error(e)
            await q.message.reply_text("❌ حدث خطأ أثناء اختيار العرض.")

# تابع التعامل مع تأكيد التوصيل وتقييم الخدمة (سيتم إضافة بوت الإدارة لاحقاً)
async def handle_delivery_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    if data.startswith("delivered_"):
        try:
            _, order_id_str = data.split("_")
            order_id = int(order_id_str)

            conn = get_conn()
            cur = conn.cursor()

            # تحقق من المندوب المنفذ
            cur.execute("SELECT selected_agent_id FROM orders WHERE id=%s", (order_id,))
            row = cur.fetchone()
            if not row or row[0] != uid:
                await q.message.reply_text("❌ أنت لست المندوب المنفذ لهذا الطلب.")
                return

            cur.execute("UPDATE orders SET status='تم التوصيل' WHERE id=%s", (order_id,))
            conn.commit()

            # إعلام المستخدم لطلب التقييم
            cur.execute("SELECT user_id FROM orders WHERE id=%s", (order_id,))
            user_id = cur.fetchone()[0]
            conn.close()

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐️ 1", callback_data=f"rate_{order_id}_1"),
                 InlineKeyboardButton("⭐️ 2", callback_data=f"rate_{order_id}_2"),
                 InlineKeyboardButton("⭐️ 3", callback_data=f"rate_{order_id}_3"),
                 InlineKeyboardButton("⭐️ 4", callback_data=f"rate_{order_id}_4"),
                 InlineKeyboardButton("⭐️ 5", callback_data=f"rate_{order_id}_5")]
            ])
            await context.bot.send_message(chat_id=user_id, text=f"✅ تم تأكيد توصيل الطلب رقم {order_id}.\nيرجى تقييم الخدمة باستخدام الأزرار أدناه.", reply_markup=kb)

        except Exception as e:
            logging.error(e)
            await q.message.reply_text("❌ حدث خطأ أثناء تأكيد التوصيل.")


async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    if data.startswith("rate_"):
        try:
            _, order_id_str, rating_str = data.split("_")
            order_id = int(order_id_str)
            rating = int(rating_str)

            conn = get_conn()
            cur = conn.cursor()

            cur.execute("SELECT selected_agent_id FROM orders WHERE id=%s", (order_id,))
            row = cur.fetchone()
            if not row:
                await q.message.reply_text("❌ طلب غير موجود.")
                return
            agent_id = row[0]

            cur.execute("INSERT INTO ratings (order_id, agent_id, rating) VALUES (%s,%s,%s)", (order_id, agent_id, rating))
            conn.commit()
            conn.close()

            await q.message.reply_text("✅ شكراً لتقييمك!")

        except Exception as e:
            logging.error(e)
            await q.message.reply_text("❌ حدث خطأ أثناء تسجيل التقييم.")


if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_role))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_offer_button, pattern="^(offer_|price_|time_)"))
    app.add_handler(CallbackQueryHandler(handle_offer_selection, pattern="^selectoffer_"))
    app.add_handler(CallbackQueryHandler(handle_delivery_confirmation, pattern="^delivered_"))
    app.add_handler(CallbackQueryHandler(handle_rating, pattern="^rate_"))

    app.run_polling()
