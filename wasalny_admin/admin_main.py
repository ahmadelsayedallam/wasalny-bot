import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("ADMIN_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # لازم تضيفه في Railway أو البيئة الخارجية

logging.basicConfig(level=logging.INFO)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ غير مصرح لك باستخدام هذا البوت.")
        return
    await update.message.reply_text("👮‍♂️ مرحباً بك في لوحة إدارة وصّلني.")

async def list_pending_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
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
            await update.message.reply_text("✅ لا يوجد مناديب في انتظار المراجعة.")
            return

        for agent in agents:
            user_id, name, gov, area, file_id = agent
            buttons = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ قبول", callback_data=f"accept_{user_id}"),
                    InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user_id}")
                ]
            ])
            caption = f"👤 الاسم: {name}\n📍 المحافظة: {gov}\n🏘️ الحي: {area}"
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=file_id,
                caption=caption,
                reply_markup=buttons
            )
    except Exception as e:
        logging.error(f"❌ خطأ في عرض المندوبين: {e}")
        await update.message.reply_text("❌ حصل خطأ أثناء عرض المندوبين.")

async def handle_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    query = update.callback_query
    await query.answer()
    data = query.data
    action, user_id = data.split("_")
    user_id = int(user_id)
    try:
        conn = get_conn()
        cur = conn.cursor()
        if action == "accept":
            cur.execute("UPDATE agents SET is_verified = TRUE WHERE user_id = %s", (user_id,))
            await query.edit_message_caption(caption="✅ تم قبول المندوب.")
            await context.bot.send_message(chat_id=user_id, text="✅ تم تفعيل حسابك كمندوب! يمكنك الآن استقبال الطلبات.")
        elif action == "reject":
            cur.execute("DELETE FROM agents WHERE user_id = %s", (user_id,))
            await query.edit_message_caption(caption="❌ تم رفض المندوب.")
            await context.bot.send_message(chat_id=user_id, text="❌ تم رفض تسجيلك كمندوب. يمكنك المحاولة مرة أخرى لاحقًا.")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطأ في اتخاذ القرار: {e}")
        await context.bot.send_message(chat_id=ADMIN_ID, text="❌ حصل خطأ أثناء تنفيذ القرار.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pending", list_pending_agents))
    app.add_handler(CallbackQueryHandler(handle_decision))
    app.run_polling()
