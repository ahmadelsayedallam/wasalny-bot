import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# 🛡️ إعدادات اللوج
logging.basicConfig(level=logging.INFO)

# 🔐 توكن بوت الإدارة من البيئة
TOKEN = os.getenv("BOT_TOKEN_ADMIN")

# ⚙️ بيانات الاتصال بقاعدة البيانات PostgreSQL
DB_URL = os.getenv("DATABASE_URL")

# 🗃️ دالة الاتصال بقاعدة البيانات
def get_db_connection():
    return psycopg2.connect(DB_URL)

# ✅ دالة البدء
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 أهلاً بك في لوحة إدارة وصّلني!\nاستخدم /pending_agents لمراجعة طلبات المندوبين.")

# 📥 عرض قائمة المندوبين في انتظار الموافقة
async def pending_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, full_name, governorate, area, id_photo_file_id
            FROM agents
            WHERE is_verified = FALSE
            ORDER BY user_id;
        """)
        agents = cursor.fetchall()
        conn.close()

        if not agents:
            await update.message.reply_text("✅ لا يوجد مندوبين في انتظار المراجعة حاليًا.")
            return

        for agent in agents:
            user_id, name, gov, area, file_id = agent

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ موافقة", callback_data=f"approve_{user_id}"),
                 InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user_id}")]
            ])

            caption = f"👤 الاسم: {name}\n📍 المحافظة: {gov}\n🏘️ الحي: {area}\n🆔 ID: {user_id}"
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=file_id, caption=caption, reply_markup=keyboard)

    except Exception as e:
        logging.error(f"❌ خطأ في جلب المندوبين: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء جلب بيانات المندوبين.")

# 🔘 التعامل مع الضغط على زر الموافقة أو الرفض
async def handle_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    decision, user_id = query.data.split("_")
    user_id = int(user_id)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if decision == "approve":
            cursor.execute("UPDATE agents SET is_verified = TRUE WHERE user_id = %s", (user_id,))
            conn.commit()
            await query.edit_message_caption(caption="✅ تمت الموافقة على هذا المندوب.")
        elif decision == "reject":
            cursor.execute("DELETE FROM agents WHERE user_id = %s", (user_id,))
            conn.commit()
            await query.edit_message_caption(caption="❌ تم رفض هذا المندوب وحذفه.")
        conn.close()

    except Exception as e:
        logging.error(f"❌ خطأ في تنفيذ القرار: {e}")
        await query.edit_message_text("❌ حدث خطأ أثناء تنفيذ القرار.")

# 🚀 تشغيل البوت
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pending_agents", pending_agents))
    app.add_handler(CallbackQueryHandler(handle_decision))

    logging.info("🚀 بوت الإدارة قيد التشغيل...")
    app.run_polling()
