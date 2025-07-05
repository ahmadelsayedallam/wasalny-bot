import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

# إعداد المتغيرات
TOKEN = os.getenv("BOT_TOKEN_ADMIN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1044357384"))

# لوج
logging.basicConfig(level=logging.INFO)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# عرض المناديب قيد المراجعة
async def show_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية.")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, full_name, governorate, area, id_photo_url FROM agents WHERE is_verified=FALSE")
    agents = cur.fetchall()
    conn.close()

    if not agents:
        return await update.message.reply_text("✅ لا يوجد مناديب في الانتظار.")

    for uid, name, gov, area, photo_url in agents:
        caption = f"👤 {name}\n🏙️ {gov} - {area}\n🆔 ID: {uid}"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ قبول", callback_data=f"approve_{uid}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"reject_{uid}")
        ]])
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_url, caption=caption, reply_markup=keyboard)

# التعامل مع زر القبول/الرفض
async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = int(data.split("_")[1])
    is_approve = data.startswith("approve_")

    try:
        conn = get_conn()
        cur = conn.cursor()

        if is_approve:
            cur.execute("UPDATE agents SET is_verified=TRUE WHERE user_id=%s", (uid,))
            await context.bot.send_message(chat_id=uid, text="✅ تم قبولك كمندوب ويمكنك الآن استقبال الطلبات.")
        else:
            cur.execute("DELETE FROM agents WHERE user_id=%s", (uid,))
            await context.bot.send_message(chat_id=uid, text="❌ تم رفض تسجيلك.")

        conn.commit()
        conn.close()

        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"📥 تم {'قبول' if is_approve else 'رفض'} المندوب {uid}.")
    except Exception as e:
        logging.error(f"❌ خطأ: {e}")
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ خطأ أثناء المعالجة:\n{e}")

# عرض الطلبات
async def show_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية.")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, governorate, area, text, status FROM orders ORDER BY id DESC LIMIT 10")
    orders = cur.fetchall()
    conn.close()

    if not orders:
        return await update.message.reply_text("✅ لا توجد طلبات حالياً.")

    for oid, uid, gov, area, txt, status in orders:
        await update.message.reply_text(f"📦 طلب #{oid}\n👤 المستخدم: {uid}\n🏙️ {gov} - {area}\n📝 {txt}\n📌 الحالة: {status}")

# تشغيل البوت
if __name__ == "__main__":
    print("🚀 تشغيل WasalnyAdminBot...")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", show_pending))
    app.add_handler(CommandHandler("pending_agents", show_pending))
    app.add_handler(CommandHandler("orders", show_orders))
    app.add_handler(CallbackQueryHandler(handle_review))

    app.run_polling()
