import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes
)

# الإعدادات
BOT_TOKEN_ADMIN = os.getenv("BOT_TOKEN_ADMIN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "123456789"))  # ← حط ID بتاعك هنا أو في .env

logging.basicConfig(level=logging.INFO)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# أمر البدء
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ ليس لديك صلاحية الوصول.")
        return
    await update.message.reply_text("👋 أهلاً بك في لوحة الإدارة.\nاستخدم الأمر /pending_agents لعرض المناديب في انتظار المراجعة.")

# عرض المناديب في انتظار التفعيل
async def pending_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ ليس لديك صلاحية الوصول.")
        return

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, full_name, governorate, area, id_photo_url
            FROM agents
            WHERE is_verified = FALSE
            ORDER BY user_id
        """)
        agents = cur.fetchall()
        cur.close()
        conn.close()

        if not agents:
            await update.message.reply_text("✅ لا يوجد مناديب قيد المراجعة.")
            return

        for agent in agents:
            user_id, full_name, governorate, area, id_photo_url = agent
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ موافقة", callback_data=f"approve:{user_id}"),
                 InlineKeyboardButton("❌ رفض", callback_data=f"reject:{user_id}")]
            ])
            text = f"""👤 <b>{full_name}</b>
📍 {governorate} - {area}
🆔 {user_id}"""

            try:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=id_photo_url,
                    caption=text,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
            except Exception as e:
                logging.error(f"❌ خطأ في عرض صورة المندوب: {e}")
                await update.message.reply_text(f"{text}\n⚠️ لم يتم عرض الصورة، راجع الرابط المخزن.")
    except Exception as e:
        logging.error(f"❌ خطأ في جلب المندوبين: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء جلب بيانات المندوبين.")

# تنفيذ الموافقة أو الرفض
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.callback_query.answer("❌ ليس لديك صلاحية.")
        return

    query = update.callback_query
    await query.answer()
    action, user_id_str = query.data.split(":")
    user_id = int(user_id_str)

    try:
        conn = get_conn()
        cur = conn.cursor()

        if action == "approve":
            cur.execute("UPDATE agents SET is_verified = TRUE WHERE user_id = %s", (user_id,))
            conn.commit()
            await query.edit_message_caption(caption="✅ تم الموافقة على هذا المندوب.")
        elif action == "reject":
            cur.execute("DELETE FROM agents WHERE user_id = %s", (user_id,))
            conn.commit()
            await query.edit_message_caption(caption="❌ تم رفض هذا المندوب وحذف بياناته.")
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطأ أثناء التحديث: {e}")
        await query.edit_message_caption(caption="❌ حدث خطأ أثناء تنفيذ الإجراء.")

# تشغيل البوت
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN_ADMIN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pending_agents", pending_agents))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling()
