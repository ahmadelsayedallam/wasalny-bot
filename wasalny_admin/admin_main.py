import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, filters
)

TOKEN = os.getenv("BOT_TOKEN_ADMIN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = 1044357384  # تم تحديثه حسب طلبك

logging.basicConfig(level=logging.INFO)

# الاتصال بقاعدة البيانات
def get_conn():
    return psycopg2.connect(DATABASE_URL)

# إرسال قائمة المندوبين المنتظرين للمراجعة
async def show_pending_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ ليس لديك صلاحية الوصول لهذا الأمر.")
        return

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT user_id, full_name, governorate, area, id_photo_file_id FROM agents WHERE is_verified = FALSE")
        agents = cur.fetchall()
        cur.close()
        conn.close()

        if not agents:
            await update.message.reply_text("✅ لا يوجد مناديب قيد المراجعة.")
            return

        for agent in agents:
            user_id, full_name, governorate, area, photo_id = agent
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ قبول", callback_data=f"approve_{user_id}"),
                    InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user_id}")
                ]
            ])
            caption = f"👤 الاسم: {full_name}\n🏙️ المحافظة: {governorate}\n📍 الحي: {area}\n🆔 ID: {user_id}"
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=caption, reply_markup=keyboard)

    except Exception as e:
        logging.error(f"❌ فشل في جلب المندوبين: {e}")
        await update.message.reply_text("❌ حصل خطأ أثناء عرض المندوبين.")

# التعامل مع أزرار القبول والرفض
async def handle_review_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if not data.startswith("approve_") and not data.startswith("reject_"):
        return

    user_id = int(data.split("_")[1])
    action = "approve" if data.startswith("approve_") else "reject"

    try:
        conn = get_conn()
        cur = conn.cursor()
        if action == "approve":
            cur.execute("UPDATE agents SET is_verified = TRUE WHERE user_id = %s", (user_id,))
            await context.bot.send_message(chat_id=user_id, text="✅ تم قبولك كمندوب! يمكنك الآن استقبال الطلبات.")
            await query.edit_message_caption(caption="✅ تم قبول هذا المندوب.")
        else:
            cur.execute("DELETE FROM agents WHERE user_id = %s", (user_id,))
            await context.bot.send_message(chat_id=user_id, text="❌ تم رفض طلبك كمندوب.")
            await query.edit_message_caption(caption="❌ تم رفض هذا المندوب.")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ فشل في مراجعة المندوب: {e}")
        await query.message.reply_text("❌ حصل خطأ أثناء تنفيذ الإجراء.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", show_pending_agents))
    app.add_handler(CallbackQueryHandler(handle_review_action))
    app.run_polling()
