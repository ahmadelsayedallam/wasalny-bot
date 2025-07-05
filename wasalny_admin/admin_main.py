import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes
)

BOT_TOKEN_ADMIN = os.getenv("BOT_TOKEN_ADMIN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = 1044357384  # غيّره لو عايز تضيف Admin تاني

logging.basicConfig(level=logging.INFO)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ ليس لديك صلاحية الوصول.")
        return
    await update.message.reply_text("✅ أهلاً بك في لوحة إدارة وصّلني.\nاكتب /pending_agents لعرض طلبات التسجيل.")

async def pending_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ ليس لديك صلاحية الوصول.")
        return

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, full_name, governorate, area, id_photo_file_id
            FROM agents
            WHERE is_verified = FALSE
        """)
        agents = cur.fetchall()
        cur.close()
        conn.close()

        if not agents:
            await update.message.reply_text("✅ لا يوجد مناديب قيد المراجعة حالياً.")
            return

        for agent in agents:
            user_id, full_name, governorate, area, photo_url = agent
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ قبول", callback_data=f"accept_{user_id}"),
                    InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user_id}")
                ]
            ])
            try:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=photo_url,
                    caption=f"👤 <b>{full_name}</b>\n📍 {governorate} - {area}\n🆔 {user_id}",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            except Exception as e:
                logging.error(f"❌ خطأ في عرض صورة المندوب: {e}")
                await update.message.reply_text(
                    f"👤 <b>{full_name}</b>\n📍 {governorate} - {area}\n🆔 {user_id}\n⚠️ لم يتم عرض الصورة، راجع الرابط المخزن.",
                    parse_mode="HTML"
                )

    except Exception as e:
        logging.error(f"❌ خطأ في جلب المندوبين: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء جلب المندوبين.")

async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if not data.startswith("accept_") and not data.startswith("reject_"):
        return

    user_id = int(data.split("_")[1])
    action = "TRUE" if data.startswith("accept") else "FALSE"
    try:
        conn = get_conn()
        cur = conn.cursor()
        if action == "TRUE":
            cur.execute("UPDATE agents SET is_verified = TRUE WHERE user_id = %s", (user_id,))
            await query.edit_message_caption(caption="✅ تم قبول المندوب.")
        else:
            cur.execute("DELETE FROM agents WHERE user_id = %s", (user_id,))
            await query.edit_message_caption(caption="❌ تم رفض المندوب.")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطأ أثناء تنفيذ الإجراء: {e}")
        await query.edit_message_caption(caption="❌ حدث خطأ أثناء تنفيذ العملية.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN_ADMIN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pending_agents", pending_agents))
    app.add_handler(CallbackQueryHandler(handle_action))
    app.run_polling()
