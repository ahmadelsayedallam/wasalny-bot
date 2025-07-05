import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

# إعداد المتغيرات
TOKEN = os.getenv("BOT_TOKEN_ADMIN")
ADMIN_ID = 1044357384  # رقم الاي دي بتاعك ثابت هنا
DATABASE_URL = os.getenv("DATABASE_URL")

# إعداد اللوج
logging.basicConfig(level=logging.INFO)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# أمر /help لعرض الأوامر المتاحة
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية.")
    help_text = (
        "/pending_agents - عرض المناديب في انتظار المراجعة\n"
        "/orders - عرض آخر الطلبات\n"
        "/delete_order <رقم_الطلب> - حذف طلب معين\n"
        "/help - عرض هذه الرسالة"
    )
    await update.message.reply_text(help_text)

# عرض المناديب في الانتظار للمراجعة
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
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ قبول", callback_data=f"approve_{uid}"),
             InlineKeyboardButton("❌ رفض", callback_data=f"reject_{uid}")]
        ])
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_url, caption=caption, reply_markup=keyboard)

# التعامل مع زر القبول أو الرفض للمناديب
async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = int(data.split("_")[1])
    is_approve = data.startswith("approve_")

    logging.info(f"📥 زرار اتداس: {data}")
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"📥 ضغطت على: {data}")

    try:
        conn = get_conn()
        cur = conn.cursor()

        if is_approve:
            cur.execute("UPDATE agents SET is_verified=TRUE WHERE user_id=%s", (uid,))
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"✅ تم قبول المندوب {uid}.")
            # إعلام المندوب أنه تم تفعيله
            await context.bot.send_message(chat_id=uid, text="✅ تم قبولك كمندوب ويمكنك الآن استقبال الطلبات.")
        else:
            cur.execute("DELETE FROM agents WHERE user_id=%s", (uid,))
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ تم رفض المندوب {uid}.")
            # إعلام المندوب أنه تم رفضه
            await context.bot.send_message(chat_id=uid, text="❌ تم رفض طلبك كمندوب.")

        conn.commit()
        conn.close()

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception as e:
            logging.warning(f"⚠️ لم أستطع إزالة أزرار الرسالة: {e}")

    except Exception as e:
        logging.error(f"❌ حدث خطأ: {e}")
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ حدث خطأ:\n{e}")

# عرض آخر 10 طلبات
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
        await update.message.reply_text(
            f"📦 طلب #{oid}\n"
            f"👤 المستخدم: {uid}\n"
            f"🏙️ {gov} - {area}\n"
            f"📝 {txt}\n"
            f"📌 الحالة: {status}"
        )

# حذف طلب معين بواسطة الاي دي
async def delete_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية.")

    if not context.args:
        return await update.message.reply_text("❗ الرجاء إرسال رقم الطلب بعد الأمر.")

    try:
        order_id = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("❌ رقم الطلب يجب أن يكون عدد صحيح.")

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM orders WHERE id=%s", (order_id,))
        deleted = cur.rowcount
        conn.commit()
        conn.close()

        if deleted == 0:
            await update.message.reply_text(f"❌ لم يتم العثور على طلب بالرقم {order_id}.")
        else:
            await update.message.reply_text(f"✅ تم حذف الطلب رقم {order_id}.")

    except Exception as e:
        logging.error(e)
        await update.message.reply_text(f"❌ حدث خطأ أثناء حذف الطلب:\n{e}")

if __name__ == "__main__":
    print("🚀 تشغيل WasalnyAdminBot...")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("pending_agents", show_pending))
    app.add_handler(CommandHandler("orders", show_orders))
    app.add_handler(CommandHandler("delete_order", delete_order))
    app.add_handler(CallbackQueryHandler(handle_review))

    app.run_polling()
