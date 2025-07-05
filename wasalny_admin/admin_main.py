import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

# ثابت الإدمن (غيره لو عاوز)
ADMIN_ID = 1044357384

# متغيرات الاتصال بقاعدة البيانات
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية لاستخدام هذا الأمر.")
    help_text = (
        "🔹 أوامر الإدارة:\n"
        "/pending_agents - عرض المندوبين في انتظار المراجعة\n"
        "/orders - عرض أحدث 10 طلبات\n"
        "/delete_order <رقم الطلب> - حذف طلب معين\n"
        "/help - عرض هذا النص"
    )
    await update.message.reply_text(help_text)

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

async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    uid = int(data.split("_")[1])
    is_approve = data.startswith("approve_")

    logging.info(f"📥 ضغط زر: {data}")
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"📥 ضغطت على: {data}")

    try:
        conn = get_conn()
        cur = conn.cursor()

        if is_approve:
            cur.execute("UPDATE agents SET is_verified=TRUE WHERE user_id=%s", (uid,))
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"✅ تم قبول المندوب {uid}.")
        else:
            cur.execute("DELETE FROM agents WHERE user_id=%s", (uid,))
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ تم رفض المندوب {uid} وحذفه.")

        conn.commit()
        conn.close()

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception as e:
            logging.warning(f"⚠️ لم أستطع إزالة أزرار الطلب: {e}")

    except Exception as e:
        logging.error(f"❌ خطأ أثناء معالجة الطلب: {e}")
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ حدث خطأ:\n{e}")

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
            f"📦 طلب #{oid}\n👤 المستخدم: {uid}\n🏙️ {gov} - {area}\n📝 {txt}\n📌 الحالة: {status}"
        )

async def delete_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية.")
    try:
        if len(context.args) != 1:
            return await update.message.reply_text("❗ استخدم: /delete_order <رقم الطلب>")
        oid = int(context.args[0])
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM orders WHERE id=%s", (oid,))
        deleted = cur.rowcount
        conn.commit()
        conn.close()
        if deleted:
            await update.message.reply_text(f"✅ تم حذف الطلب رقم {oid}.")
        else:
            await update.message.reply_text(f"❌ لم يتم العثور على طلب برقم {oid}.")
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ حدث خطأ أثناء حذف الطلب.")

if __name__ == "__main__":
    print("🚀 تشغيل WasalnyAdminBot...")
    app = ApplicationBuilder().token(os.getenv("BOT_TOKEN_ADMIN")).build()

    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("pending_agents", show_pending))
    app.add_handler(CommandHandler("orders", show_orders))
    app.add_handler(CommandHandler("delete_order", delete_order))
    app.add_handler(CallbackQueryHandler(handle_review))

    app.run_polling()
