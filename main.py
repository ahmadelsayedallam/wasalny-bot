import os
import logging
import psycopg2
from telegram import (
    Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)

# إعداد التوكن وقاعدة البيانات
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

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_states[user_id] = None
    keyboard = [[KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]]
    await update.message.reply_text("أهلاً بيك! اختار دورك:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# معالجة كل الرسائل النصية
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # ===== مستخدم =====
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
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, governorate, area, order_text, "قيد الانتظار"))
            conn.commit()
            cur.close()
            conn.close()
            logging.info(f"✅ تم تسجيل الطلب من {user_id}: {order_text}")
            await update.message.reply_text("✅ تم تسجيل طلبك! سيتم إرسال الطلب للمناديب القريبين.")
        except Exception as e:
            logging.error(f"❌ فشل حفظ الطلب: {e}")
            await update.message.reply_text("❌ حصل خطأ أثناء تسجيل الطلب.")
        user_states[user_id] = None
        user_data[user_id] = {}
        return

    # ===== مندوب =====
    if text == "🚚 مندوب":
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

# 📸 استقبال صورة البطاقة
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_states.get(user_id) == "awaiting_id_photo":
        photo = update.message.photo[-1]
        photo_file = await context.bot.get_file(photo.file_id)
        photo_url = f"https://api.telegram.org/file/bot{context.bot.token}/{photo_file.file_path}"


        full_name = user_data[user_id].get("full_name")
        governorate = user_data[user_id].get("governorate")
        area = user_data[user_id].get("area")

        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO agents (user_id, full_name, governorate, area, id_photo_url, is_verified)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, full_name, governorate, area, photo_url, False))
            conn.commit()
            cur.close()
            conn.close()
            logging.info(f"📸 تم استقبال صورة من {user_id}, url: {photo_url}")
            await update.message.reply_text("✅ تم استلام البطاقة. سيتم مراجعتها من الإدارة قبل تفعيل حسابك.")
        except Exception as e:
            logging.error(f"❌ فشل في تسجيل المندوب: {e}")
            await update.message.reply_text("❌ حصل خطأ أثناء حفظ بياناتك.")
        user_states[user_id] = None
        user_data[user_id] = {}

# تشغيل البوت
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()
