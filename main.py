import os
import logging
import psycopg2
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]]
    await update.message.reply_text("أهلاً بيك! اختار دورك:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    user_states[update.effective_user.id] = None

async def handle_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text == "🚶‍♂️ مستخدم":
        user_states[user_id] = "awaiting_governorate"
        await update.message.reply_text("اختار محافظتك:", reply_markup=ReplyKeyboardMarkup([[g] for g in GOVERNORATES], resize_keyboard=True))
        return

    if user_states.get(user_id) == "awaiting_governorate":
        if text in GOVERNORATES:
            user_data[user_id] = {"governorate": text}
            user_states[user_id] = "awaiting_area"
            await update.message.reply_text("اختار الحي:", reply_markup=ReplyKeyboardMarkup([[a] for a in AREAS], resize_keyboard=True))
        else:
            await update.message.reply_text("❌ اختر محافظة من القائمة.")
        return

    if user_states.get(user_id) == "awaiting_area":
        if text in AREAS:
            user_data[user_id]["area"] = text
            user_states[user_id] = "awaiting_order"
            await update.message.reply_text("اكتب تفاصيل طلبك:", reply_markup=ReplyKeyboardRemove())
        else:
            await update.message.reply_text("❌ اختر حي من القائمة.")
        return

    if user_states.get(user_id) == "awaiting_order":
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO orders (user_id, governorate, area, text, status)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, user_data[user_id]["governorate"], user_data[user_id]["area"], text, "قيد الانتظار"))
            conn.commit()
            await update.message.reply_text("✅ تم تسجيل طلبك! سيتم إرسال الطلب للمناديب القريبين.")
        except Exception as e:
            logging.error(f"❌ فشل حفظ الطلب: {e}")
            await update.message.reply_text("❌ حصل خطأ أثناء حفظ الطلب.")
        finally:
            cur.close()
            conn.close()
            user_states[user_id] = None
            user_data[user_id] = {}
        return

    if text == "🚚 مندوب":
        user_states[user_id] = "awaiting_name"
        await update.message.reply_text("اكتب اسمك الكامل:")
        return

    if user_states.get(user_id) == "awaiting_name":
        user_data[user_id] = {"full_name": text}
        user_states[user_id] = "awaiting_governorate_agent"
        await update.message.reply_text("اختار محافظتك:", reply_markup=ReplyKeyboardMarkup([[g] for g in GOVERNORATES], resize_keyboard=True))
        return

    if user_states.get(user_id) == "awaiting_governorate_agent":
        if text in GOVERNORATES:
            user_data[user_id]["governorate"] = text
            user_states[user_id] = "awaiting_area_agent"
            await update.message.reply_text("اختار الحي:", reply_markup=ReplyKeyboardMarkup([[a] for a in AREAS], resize_keyboard=True))
        else:
            await update.message.reply_text("❌ اختر محافظة من القائمة.")
        return

    if user_states.get(user_id) == "awaiting_area_agent":
        if text in AREAS:
            user_data[user_id]["area"] = text
            user_states[user_id] = "awaiting_photo"
            await update.message.reply_text("📸 ارفع صورة بطاقتك.")
        else:
            await update.message.reply_text("❌ اختر حي من القائمة.")
        return

    await update.message.reply_text("من فضلك ابدأ بـ /start")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_states.get(user_id) == "awaiting_photo":
        photo = update.message.photo[-1]
        file_id = photo.file_id
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO agents (user_id, full_name, governorate, area, id_photo_file_id, is_verified)
                VALUES (%s, %s, %s, %s, %s, FALSE)
            """, (
                user_id,
                user_data[user_id]["full_name"],
                user_data[user_id]["governorate"],
                user_data[user_id]["area"],
                file_id
            ))
            conn.commit()
            await update.message.reply_text("✅ تم استلام بطاقتك، في انتظار المراجعة.")
        except Exception as e:
            logging.error(f"❌ فشل حفظ المندوب: {e}")
            await update.message.reply_text("❌ حصل خطأ أثناء تسجيل بياناتك.")
        finally:
            cur.close()
            conn.close()
            user_states[user_id] = None
            user_data[user_id] = {}

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()
