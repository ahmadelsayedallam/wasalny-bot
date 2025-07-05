import os
import logging
import psycopg2
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

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
    uid = update.effective_user.id
    keyboard = [[KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]]
    await update.message.reply_text("أهلاً بيك! اختار دورك:", 
                                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    user_states[uid] = None

async def handle_user_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    # خطوات المستخدم ...
    if text == "🚚 مندوب":
        user_states[uid] = "awaiting_agent_name"
        await update.message.reply_text("اكتب اسمك الكامل:")
        return
    if user_states.get(uid) == "awaiting_agent_name":
        user_data[uid] = {"full_name": text}
        user_states[uid] = "awaiting_agent_governorate"
        await update.message.reply_text("اختار محافظتك:", 
                                        reply_markup=ReplyKeyboardMarkup([[g] for g in GOVERNORATES], resize_keyboard=True))
        return
    if user_states.get(uid) == "awaiting_agent_governorate":
        if text not in GOVERNORATES:
            await update.message.reply_text("❌ اختر محافظة من القائمة.")
            return
        user_data[uid]["governorate"] = text
        user_states[uid] = "awaiting_agent_area"
        await update.message.reply_text("اختار الحي:", 
                                        reply_markup=ReplyKeyboardMarkup([[a] for a in AREAS], resize_keyboard=True))
        return
    if user_states.get(uid) == "awaiting_agent_area":
        if text not in AREAS:
            await update.message.reply_text("❌ اختر حي من القائمة.")
            return
        user_data[uid]["area"] = text
        user_states[uid] = "awaiting_id_photo"
        await update.message.reply_text("📸 ارفع صورة بطاقتك لمراجعتها قبل التفعيل.")
        return

    await update.message.reply_text("من فضلك ابدأ بـ /start")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if user_states.get(uid) == "awaiting_id_photo":
        photo = update.message.photo[-1]
        file_id = photo.file_id
        logging.info(f"📸 استقبلت صورة من {uid}, file_id={file_id}")

        info = user_data[uid]
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO agents 
                (user_id, full_name, governorate, area, id_photo_file_id, is_verified)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (uid, info["full_name"], info["governorate"], info["area"], file_id, False))
            conn.commit()
            cur.close()
            conn.close()
            await update.message.reply_text("✅ تم استلام البطاقة، انتظر موافقة الإدارة.")
        except Exception as e:
            logging.error(f"❌ خطأ في حفظ المندوب: {e}")
            await update.message.reply_text("❌ حصل خطأ، حاول تاني.")
        user_states[uid] = None
        user_data.pop(uid, None)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_role))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()
