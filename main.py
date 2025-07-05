import os
import logging
import psycopg2
import cloudinary
import cloudinary.uploader
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)

# إعداد البيئة
TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

cloudinary.config(
    cloud_name="dje6mo6va",
    api_key="978139836161399",
    api_secret="YZjvZOy7lit18QUNeKZG77BBg0k"
)

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [[KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]]
    await update.message.reply_text("أهلاً بيك! اختار دورك:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    user_states[user_id] = None

# ... باقي التعامل مع المستخدم العادي (مش هنعدله)

async def handle_user_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

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

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_states.get(user_id) == "awaiting_id_photo":
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        file_path = f"{user_id}_id.jpg"
        await file.download_to_drive(file_path)

        try:
            upload_result = cloudinary.uploader.upload(file_path)
            image_url = upload_result.get("secure_url")

            full_name = user_data[user_id].get("full_name")
            governorate = user_data[user_id].get("governorate")
            area = user_data[user_id].get("area")

            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO agents (user_id, full_name, governorate, area, id_photo_url, is_verified)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, full_name, governorate, area, image_url, False))
            conn.commit()
            cur.close()
            conn.close()

            await update.message.reply_text("✅ تم استلام البطاقة. سيتم مراجعتها من الإدارة قبل تفعيل حسابك.")
            logging.info(f"📸 تم رفع صورة المندوب: {image_url}")
        except Exception as e:
            logging.error(f"❌ فشل في تسجيل المندوب: {e}")
            await update.message.reply_text("❌ حصل خطأ أثناء حفظ بياناتك.")
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

        user_states[user_id] = None
        user_data[user_id] = {}

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_role))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()
