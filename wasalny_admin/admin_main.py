import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

# إعدادات البيئة
TOKEN = os.getenv("BOT_TOKEN_ADMIN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1044357384"))

logging.basicConfig(level=logging.INFO)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# عرض المندوبين قيد المراجعة
async def show_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية.")
    
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, full_name, governorate, area, id_photo_url FROM agents WHERE is_verified=FALSE")
    agents = cur.fetchall()
    conn.close()

    if not agents:
        return await update.message.reply_text("✅ لا يوجد مناديب للمراجعة.")

    for uid, full_name, gov, area, photo_url in agents:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ قبول", callback_data=f"approve_{uid}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"reject_{uid}")
        ]])
        caption = f"👤 {full_name}\n🏙️ {gov} - {area}\nID: {uid}"
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_url, caption=caption, reply_markup=kb)

# معالجة زر القبول أو الرفض
async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    uid = int(data.split("_")[1])
    is_approve = data.startswith("approve_")

    print("📥 زرار اتداس:", data)
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"📥 ضغطت على: {data}")

    try:
        conn = get_conn()
        cur = conn.cursor()

        if is_approve:
            cur.execute("UPDATE agents SET is_verified=TRUE WHERE user_id=%s", (uid,))
            await context.bot.send_message(chat_id=uid, text="✅ تم قبولك كمندوب.")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"✅ تم **قبول** المندوب {uid}.")
        else:
            cur.execute("DELETE FROM agents WHERE user_id=%s", (uid,))
            await context.bot.send_message(chat_id=uid, text="❌ تم رفضك.")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ تم **رفض** المندوب {uid}.")

        conn.commit()
        conn.close()

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception as e:
            logging.warning(f"❗ فشل في إزالة الزرار: {e}")

    except Exception as e:
        logging.error(f"❌ حصل خطأ أثناء معالجة الطلب: {e}")
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ حصل خطأ:\n{e}")

# عرض الطلبات الأخيرة
async def show_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية.")
    
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, governorate, area, text, status FROM orders ORDER BY id DESC LIMIT 10")
    orders = cur.fetchall()
    conn.close()

    if not orders:
        return await update.message.reply_text("✅ لا توجد طلبات.")
    
    for oid, uid, gov, area, text, status in orders:
        await update.message.reply_text(
            f"📦 طلب #{oid}\n👤 المستخدم: {uid}\n🏙️ {gov} - {area}\n📝 {text}\n📌 الحالة: {status}"
        )

# تشغيل البوت
if __name__ == "__main__":
    print("🚀 تشغيل بوت الإدارة...")
    print("🔐 التوكن المستخدم:", TOKEN)
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", show_pending))
    app.add_handler(CommandHandler("pending_agents", show_pending))
    app.add_handler(CommandHandler("orders", show_orders))
    app.add_handler(CallbackQueryHandler(handle_review))

    app.run_polling()
