import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN_ADMIN = os.getenv("BOT_TOKEN_ADMIN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_USER_ID = 1044357384  # حط الـ Telegram user ID بتاعك هنا

logging.basicConfig(level=logging.INFO)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ غير مصرح لك باستخدام هذا البوت.")
        return

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, full_name, governorate, area, id_photo_file_id
            FROM agents
            WHERE is_verified = FALSE
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            await update.message.reply_text("✅ لا يوجد مناديب في الانتظار.")
            return

        for row in rows:
            user_id, full_name, governorate, area, file_id = row
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ موافقة", callback_data=f"approve_{user_id}"),
                 InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user_id}")]
            ])
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=file_id,
                caption=f"🆔 {user_id}\n👤 {full_name}\n📍 {governorate} - {area}",
                reply_markup=keyboard
            )
    except Exception as e:
        logging.error(f"❌ خطأ في جلب المندوبين: {e}")
        await update.message.reply_text("❌ حصل خطأ أثناء عرض المندوبين.")

async def handle_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, user_id = query.data.split("_")
    try:
        conn = get_conn()
        cur = conn.cursor()
        if action == "approve":
            cur.execute("UPDATE agents SET is_verified = TRUE WHERE user_id = %s", (user_id,))
            await query.edit_message_caption(caption="✅ تمت الموافقة على المندوب.")
        else:
            cur.execute("DELETE FROM agents WHERE user_id = %s", (user_id,))
            await query.edit_message_caption(caption="❌ تم رفض المندوب وحذف بياناته.")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ فشل في تحديث حالة المندوب: {e}")
        await query.edit_message_caption(caption="❌ حصل خطأ أثناء تنفيذ الإجراء.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN_ADMIN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_decision))
    app.run_polling()
