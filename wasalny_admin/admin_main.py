import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN_ADMIN = os.getenv("BOT_TOKEN_ADMIN")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, full_name, governorate, area, id_photo_file_id
            FROM agents WHERE is_verified = FALSE ORDER BY user_id
        """)
        agents = cur.fetchall()
        cur.close()
        conn.close()

        if not agents:
            await update.message.reply_text("✅ لا يوجد مناديب في انتظار المراجعة حالياً.")
            return

        for agent in agents:
            user_id, full_name, governorate, area, file_url = agent
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ الموافقة", callback_data=f"approve:{user_id}"),
                InlineKeyboardButton("❌ الرفض", callback_data=f"reject:{user_id}")
            ]])
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=file_url,
                caption=f"👤 الاسم: {full_name}\n📍 المحافظة: {governorate}\n🏘️ الحي: {area}\n🆔 {user_id}",
                reply_markup=keyboard
            )
    except Exception as e:
        logging.error(f"❌ خطأ في جلب المندوبين: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء جلب بيانات المندوبين.")

async def handle_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, user_id = query.data.split(":")
    user_id = int(user_id)

    try:
        conn = get_conn()
        cur = conn.cursor()
        if action == "approve":
            cur.execute("UPDATE agents SET is_verified = TRUE WHERE user_id = %s", (user_id,))
            await query.edit_message_caption(caption="✅ تم الموافقة على هذا المندوب.")
        else:
            cur.execute("DELETE FROM agents WHERE user_id = %s", (user_id,))
            await query.edit_message_caption(caption="❌ تم رفض هذا المندوب وحذف بياناته.")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ فشل التحديث: {e}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ حصل خطأ أثناء تنفيذ القرار.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN_ADMIN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_decision))
    app.run_polling()
