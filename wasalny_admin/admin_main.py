import os
import logging
import psycopg2
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN_ADMIN")
DATABASE_URL = os.getenv("DATABASE_URL")
logging.basicConfig(level=logging.INFO)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 أهلاً! استخدم /pending_agents لمراجعة المندوبين.")

async def pending_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, full_name, governorate, area, id_photo_file_id
            FROM agents WHERE is_verified = FALSE
            ORDER BY user_id
        """)
        rows = cur.fetchall()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطأ جلب بيانات: {e}")
        await update.message.reply_text("❌ حدث خطأ في جلب المندوبين.")
        return

    if not rows:
        await update.message.reply_text("✅ لا يوجد مندوبين في انتظار المراجعة.")
        return

    for user_id, name, gov, area, file_id in rows:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ موافقة", callback_data=f"approve:{user_id}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"reject:{user_id}")
        ]])
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=file_id,
            caption=f"👤 {name}\n📍 {gov} - {area}\n🆔 {user_id}",
            reply_markup=kb
        )

async def handle_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, uid = query.data.split(":")
    uid = int(uid)
    try:
        conn = get_conn()
        cur = conn.cursor()
        if action == "approve":
            cur.execute("UPDATE agents SET is_verified = TRUE WHERE user_id = %s", (uid,))
            await query.edit_message_caption("✅ تم تفعيل هذا المندوب.")
        else:
            cur.execute("DELETE FROM agents WHERE user_id = %s", (uid,))
            await query.edit_message_caption("❌ تم رفض هذا المندوب.")
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطأ تنفيذ القرار: {e}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ خطأ! حاول تاني.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pending_agents", pending_agents))
    app.add_handler(CallbackQueryHandler(handle_decision))
    app.run_polling()
