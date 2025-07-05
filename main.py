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

# حالة المستخدم والبيانات المؤقتة
user_states = {}
user_data = {}

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

# معالجة خطوات بيانات المستخدم والطلب
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
            # إدخال الطلب
            cur.execute("""
                INSERT INTO orders (user_id, governorate, area, address, phone, text, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """, (uid, gov, area, address, phone, text, "قيد الانتظار"))
            oid = cur.fetchone()[0]
            conn.commit()

            # إرسال الطلب للمناديب النشيطين في المحافظة والحي
            cur.execute("""
                SELECT user_id FROM agents WHERE is_verified=TRUE AND governorate=%s AND area=%s
            """, (gov, area))
            agents = cur.fetchall()
            conn.close()

            for (aid,) in agents:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("📝 عرض", callback_data=f"offer_{oid}_{uid}_{aid}")]])
                await context.bot.send_message(chat_id=aid, text=f"طلب جديد من {area}:\n{address}\n\n{txt}", reply_markup=kb)

            await update.message.reply_text("✅ تم إرسال الطلب وسيتم التواصل معك قريباً.")
        except Exception as e:
            logging.error(e)
            await update.message.reply_text("❌ حصل خطأ أثناء إرسال الطلب.")
        user_states[uid] = None
        user_data[uid] = {}
        return

    # ... هنا باقي حالات تسجيل المندوب كما قبل

# استقبل عروض المندوب
async def handle_offer_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    uid = q.from_user.id

    if d.startswith("offer_"):
        parts = d.split("_")
        if len(parts) != 4:
            await q.message.reply_text("❌ خطأ في البيانات.")
            return
        _, oid_str, user_id_str, aid_str = parts
        oid = int(oid_str)
        user_id = int(user_id_str)
        aid = int(aid_str)
        user_data[uid] = {"order_id": oid, "user_id": user_id, "agent_id": aid}
        user_states[uid] = "awaiting_offer_price"
        kb = [[InlineKeyboardButton(p, callback_data=f"price_{p}")] for p in PRICE_OPTS]
        await q.message.reply_text("اختار السعر:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if d.startswith("price_"):
        pr = d.split("_",1)[1]
        user_data[uid]["price"] = pr
        user_states[uid] = "awaiting_offer_time"
        kb = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in TIME_OPTS]
        await q.message.reply_text("اختار الزمن:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if d.startswith("time_"):
        tm = d.split("_",1)[1]
        info = user_data.get(uid, {})
        oid = info.get("order_id")
        pr = info.get("price")
        aid = info.get("agent_id")
        try:
            conn = get_conn()
            cur = conn.cursor()
            # سجل العرض في قاعدة البيانات
            cur.execute("""
                INSERT INTO offers (order_id, agent_id, price, estimated_time) VALUES (%s,%s,%s,%s)
            """, (oid, aid, pr, tm))
            conn.commit()
            conn.close()
            await q.message.reply_text("✅ تم إرسال العرض.")
        except Exception as e:
            logging.error(e)
            await q.message.reply_text("❌ فشل في إرسال العرض.")
        user_states[uid] = None
        user_data[uid] = {}
        return

# هنا جزء عرض العروض على المستخدم مع أزرار قبول ورفض لكل عرض (دالة جديدة)
async def show_offers_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        conn = get_conn()
        cur = conn.cursor()
        # جلب آخر طلب قيد الانتظار للمستخدم
        cur.execute("SELECT id FROM orders WHERE user_id=%s AND status='قيد الانتظار' ORDER BY id DESC LIMIT 1", (uid,))
        row = cur.fetchone()
        if not row:
            return await update.message.reply_text("❌ ليس لديك طلبات في انتظار العروض.")
        oid = row[0]

        # جلب عروض الطلب
        cur.execute("SELECT agent_id, price, estimated_time FROM offers WHERE order_id=%s", (oid,))
        offers = cur.fetchall()
        conn.close()

        if not offers:
            return await update.message.reply_text("❌ لم يستقبل طلبك أي عروض بعد، يرجى الانتظار.")

        buttons = []
        for (agent_id, price, est_time) in offers:
            text = f"مندوب {agent_id} - السعر: {price} - الوقت المتوقع: {est_time}"
            callback_accept = f"accept_offer_{oid}_{agent_id}"
            callback_reject = f"reject_offer_{oid}_{agent_id}"
            buttons.append([
                InlineKeyboardButton(f"✔️ قبول - {price}", callback_data=callback_accept),
                InlineKeyboardButton("❌ رفض", callback_data=callback_reject)
            ])

        kb = InlineKeyboardMarkup(buttons)
        await update.message.reply_text("اختار العرض المناسب لك:", reply_markup=kb)

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ حدث خطأ أثناء جلب العروض.")

# استقبال رد المستخدم على قبول أو رفض العرض
async def handle_offer_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    try:
        parts = data.split("_")
        if len(parts) != 4:
            await q.message.reply_text("❌ خطأ في البيانات.")
            return
        action, _, oid_str, aid_str = parts
        oid = int(oid_str)
        aid = int(aid_str)
        conn = get_conn()
        cur = conn.cursor()

        if action == "accept":
            # حدث الطلب بأنه قيد التنفيذ مع المندوب المختار
            cur.execute("UPDATE orders SET status='قيد التنفيذ', selected_agent_id=%s WHERE id=%s", (aid, oid))
            conn.commit()

            # جلب بيانات المستخدم للطلب
            cur.execute("SELECT user_id, governorate, area, address, phone, text FROM orders WHERE id=%s", (oid,))
            order_info = cur.fetchone()
            user_id, gov, area, address, phone, order_text = order_info

            # إبلاغ المندوب أنه تم اختيار عرضه + إرسال بيانات المستخدم
            cur.execute("SELECT user_id FROM agents WHERE user_id=%s", (aid,))
            row = cur.fetchone()
            if row:
                msg = (
                    f"🎉 تم اختيارك لتنفيذ الطلب رقم {oid}.\n"
                    f"بيانات المستخدم:\n"
                    f"العنوان: {address}\n"
                    f"رقم التليفون: {phone}\n"
                    f"تفاصيل الطلب: {order_text}"
                )
                await context.bot.send_message(chat_id=aid, text=msg)

            # إبلاغ المستخدم
            await q.message.edit_text("✅ تم قبول العرض، والمندوب سيتواصل معك قريبًا.")

            # حذف العروض الأخرى لنفس الطلب
            cur.execute("DELETE FROM offers WHERE order_id=%s AND agent_id!=%s", (oid, aid))
            conn.commit()
            conn.close()

        elif action == "reject":
            # حذف العرض المرفوض فقط
            cur.execute("DELETE FROM offers WHERE order_id=%s AND agent_id=%s", (oid, aid))
            conn.commit()
            conn.close()

            await q.message.edit_text("تم رفض العرض.")

        else:
            await q.message.reply_text("❌ حدث خطأ في اختيار العرض.")
    except Exception as e:
        logging.error(e)
        await q.message.reply_text("❌ حدث خطأ أثناء معالجة قرار العرض.")

# أمر لإبلاغ المندوب انه وصل التوصيل
async def delivery_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # تأكد أن هذا هو مندوب ولديه طلب قيد التنفيذ
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id FROM orders WHERE selected_agent_id=%s AND status='قيد التنفيذ' LIMIT 1", (uid,))
        row = cur.fetchone()
        if not row:
            return await update.message.reply_text("❌ ليس لديك طلبات قيد التنفيذ.")
        oid = row[0]

        # تحديث حالة الطلب
        cur.execute("UPDATE orders SET status='بانتظار تقييم المستخدم' WHERE id=%s", (oid,))
        conn.commit()
        conn.close()

        # إبلاغ المستخدم أن التوصيل تم
        cur.execute("SELECT user_id FROM orders WHERE id=%s", (oid,))
        user_id = cur.fetchone()[0]
        await context.bot.send_message(chat_id=user_id, text=f"📦 تم توصيل الطلب رقم {oid}. رجاءً قيم المندوب الآن باستخدام /rate {oid}")

        await update.message.reply_text("✅ تم تسجيل أن التوصيل تم.")

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ حدث خطأ أثناء تحديث حالة التوصيل.")

# استقبال تقييم المستخدم
async def rate_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = context.args
    if len(args) < 1:
        return await update.message.reply_text("❗ استخدم الأمر بالشكل: /rate <رقم الطلب>\nمثال: /rate 12")
    try:
        oid = int(args[0])
    except:
        return await update.message.reply_text("❌ رقم طلب غير صحيح.")

    if len(context.args) < 2:
        return await update.message.reply_text("❗ اكتب تقييمك من 1 إلى 5 بعد رقم الطلب\nمثال: /rate 12 5")

    try:
        rating = int(context.args[1])
        if rating < 1 or rating > 5:
            raise ValueError
    except:
        return await update.message.reply_text("❌ التقييم يجب أن يكون عدد بين 1 و 5.")

    try:
        conn = get_conn()
        cur = conn.cursor()

        # تحقق أن الطلب للحساب
        cur.execute("SELECT selected_agent_id, status FROM orders WHERE id=%s AND user_id=%s", (oid, uid))
        row = cur.fetchone()
        if not row:
            return await update.message.reply_text("❌ الطلب غير موجود أو لا يخصك.")
        agent_id, status = row
        if status != "بانتظار تقييم المستخدم":
            return await update.message.reply_text("❌ لا يمكنك تقييم هذا الطلب الآن.")

        # حفظ التقييم
        cur.execute("INSERT INTO ratings (order_id, agent_id, user_id, rating) VALUES (%s, %s, %s, %s)",
                    (oid, agent_id, uid, rating))
        # تحديث حالة الطلب إلى "تم التقييم"
        cur.execute("UPDATE orders SET status='تم التقييم' WHERE id=%s", (oid,))
        conn.commit()
        conn.close()
        await update.message.reply_text("✅ شكراً على تقييمك.")
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ حدث خطأ أثناء تسجيل التقييم.")

# إضافة الهاندلرز في main:
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_role))
    app.add_handler(CallbackQueryHandler(handle_offer_button, pattern=r"^offer_"))
    app.add_handler(CallbackQueryHandler(handle_offer_decision, pattern=r"^(accept|reject)_offer_"))
    app.add_handler(CommandHandler("show_offers", show_offers_to_user))  # اختياري
    app.add_handler(CommandHandler("delivery_done", delivery_done))  # المندوب يكتب الامر لما يوصل
    app.add_handler(CommandHandler("rate", rate_agent))  # المستخدم يكتب التقييم

    # ... ممكن handlers إضافية حسب الحاجة

    app.run_polling()
