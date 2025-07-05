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
                await context.bot.send_message(chat_id=aid, text=f"طلب جديد من {area}:", reply_markup=kb)
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

    if d.startswith("offer_"):
        parts = d.split("_")
        if len(parts) != 3:
            await q.message.reply_text("❌ خطأ في بيانات العرض.")
            return
        oid = int(parts[1])
        user_data[uid] = {"order_id": oid}
        user_states[uid] = "awaiting_offer_price"
        kb = [[InlineKeyboardButton(p, callback_data=f"price_{p}")] for p in PRICE_OPTS]
        return await q.message.reply_text("اختار السعر:", reply_markup=InlineKeyboardMarkup(kb))

    if d.startswith("price_"):
        pr = d.split("_", 1)[1]
        user_data[uid]["price"] = pr
        user_states[uid] = "awaiting_offer_time"
        kb = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in TIME_OPTS]
        return await q.message.reply_text("اختار الزمن:", reply_markup=InlineKeyboardMarkup(kb))

    if d.startswith("time_"):
        tm = d.split("_", 1)[1]
        info = user_data.get(uid, {})
        oid = info.get("order_id")
        pr = info.get("price")
        try:
            conn = get_conn()
            cur = conn.cursor()
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

# عرض العروض للمستخدم لاختيار مندوب
async def handle_user_offer_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    if not data.startswith("select_offer_"):
        return

    parts = data.split("_")
    if len(parts) != 3:
        await q.message.reply_text("❌ خطأ في اختيار العرض.")
        return

    oid = int(parts[2])
    selected_agent_id = int(parts[1])

    try:
        conn = get_conn()
        cur = conn.cursor()
        # تحديث حالة الطلب وتحديد المندوب المختار
        cur.execute("UPDATE orders SET status='قيد التنفيذ', selected_agent_id=%s WHERE id=%s", (selected_agent_id, oid))
        conn.commit()

        # حذف العروض الأخرى الخاصة بالطلب
        cur.execute("DELETE FROM offers WHERE order_id=%s AND agent_id != %s", (oid, selected_agent_id))
        conn.commit()

        # جلب بيانات المندوب المختار
        cur.execute("SELECT user_id FROM agents WHERE user_id=%s", (selected_agent_id,))
        row = cur.fetchone()

        conn.close()

        # إرسال إشعار للمندوب المختار
        if row:
            await context.bot.send_message(chat_id=selected_agent_id, text=f"🎉 تم اختيارك لتنفيذ الطلب رقم {oid}.")

        # إعلام المستخدم
        await q.message.reply_text(f"✅ تم اختيار المندوب رقم {selected_agent_id} لتنفيذ طلبك.")

    except Exception as e:
        logging.error(e)
        await q.message.reply_text("❌ حدث خطأ أثناء اختيار المندوب.")

# إضافة إلغاء الطلب للمستخدم (جزء من الطلبات الممكن إلغاؤها)
async def handle_user_cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, text, status FROM orders 
            WHERE user_id=%s AND status IN ('قيد الانتظار', 'لم يتم اختيار مندوب')
            ORDER BY id DESC
        """, (uid,))
        orders = cur.fetchall()
        conn.close()
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ حدث خطأ أثناء جلب الطلبات.")
        return

    if not orders:
        await update.message.reply_text("❌ لا توجد طلبات يمكنك إلغاؤها.")
        return

    keyboard = []
    for oid, txt, status in orders:
        keyboard.append([InlineKeyboardButton(f"طلب #{oid} - {status}", callback_data=f"cancel_order_{oid}")])

    await update.message.reply_text("اختر الطلب الذي تريد إلغاؤه:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_cancel_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    if not data.startswith("cancel_order_"):
        return

    oid = int(data.split("_")[-1])

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT status FROM orders WHERE id=%s AND user_id=%s AND status IN ('قيد الانتظار', 'لم يتم اختيار مندوب')
        """, (oid, uid))
        row = cur.fetchone()
        if not row:
            await query.message.reply_text("❌ هذا الطلب لا يمكن إلغاؤه أو غير موجود.")
            conn.close()
            return

        cur.execute("UPDATE orders SET status='ملغى' WHERE id=%s", (oid,))
        conn.commit()
        conn.close()

        await query.message.reply_text(f"✅ تم إلغاء الطلب رقم {oid} بنجاح.")

    except Exception as e:
        logging.error(e)
        await query.message.reply_text("❌ حدث خطأ أثناء إلغاء الطلب.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_role))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_offer_button, pattern=r"^(offer_|price_|time_)"))
    app.add_handler(CallbackQueryHandler(handle_user_offer_selection, pattern=r"^select_offer_"))
    app.add_handler(CommandHandler("cancel_my_order", handle_user_cancel_order))
    app.add_handler(CallbackQueryHandler(handle_cancel_order_callback, pattern=r"^cancel_order_"))

    app.run_polling()
