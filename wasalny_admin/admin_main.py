import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# الإعدادات
BOT_TOKEN_ADMIN = os.getenv("BOT_TOKEN_ADMIN")
DATABASE_URL = os.getenv("DATABASE_URL")

# تشغيل اللوج
logging.basicConfig(level=logging.INFO)

# يوزر الآدمن فقط المسموح له
ADMIN_USER_ID = 1044357384  # ← عدله لو عايز تغير الآدمن

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# التحقق إن المستخدم هو الآدمن
def is_admin(user_id):
    return user_id == ADMIN_USER_ID

# أمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ غير مصرح لك باستخدام هذا البوت.")
        return
    await update.message.reply_text("مرحبًا بك في لوحة إدارة المندوبين.\nاكتب الأمر: pending_agents")

# عرض المندوبين غير المراجَعين
async def pending_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ غير مصرح لك.")
        return

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, full_name, governorate, area, id_photo_url, is_verified
            FROM agents
            WHERE is_verified = FALSE
            ORDER BY user_id
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            await update.message.reply_text("✅ لا يوجد مناديب في الانتظار.")
            return

        for row in rows:
            user_id, full_name, governorate, area, photo_url, _ = row
            caption = f"👤 الاسم: {full_name}\n🏙️ المحافظة: {governorate}\n📍 الحي: {area}\n🆔 ID: {user_id}"
            keyboard = [
                [
                    InlineKeyboardButton("✅ موافقة", callback_data=f"approve:{user_id}"),
                    InlineKeyboardButton("❌ رفض", callback_data=f"reject:{user_id}")
                ]
            ]
            try:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=photo_url,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                logging.error(f"❌ خطأ في عرض صورة المندوب: {e}")
                await update.message.reply_text(f"❌ حصل خطأ في عرض المندوب ID: {user_id}")
    except Exception as e:
        logging.error(f"❌ خطأ في جلب المندوبين: {e}")
        await update.message.reply_text("❌ حصل خطأ في جلب بيانات المندوبين.")

# التعامل مع الضغط على زر موافقة أو رفض
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.callback_query.answer("❌ غير مصرح لك.")
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
            await query.edit_message_caption(caption="✅ تم تفعيل حساب المندوب.")
        elif action == "reject":
            cur.execute("DELETE FROM agents WHERE user_id = %s", (user_id,))
            await query.edit_message_caption(caption="❌ تم رفض المندوب وحذف بياناته.")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطأ في تعديل حالة المندوب: {e}")
        await query.message.reply_text("❌ حصل خطأ أثناء تنفيذ العملية.")

# تشغيل البوت
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN_ADMIN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pending_agents", pending_agents))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling()
