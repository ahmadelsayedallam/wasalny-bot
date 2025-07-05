import os
import logging
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("ADMIN_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("1044357384"))

def get_conn():
    return psycopg2.connect(DATABASE_URL)

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = (
        "/list_pending_agents - عرض المناديب في انتظار المراجعة\n"
        "/approve_agent <user_id> - الموافقة على مندوب\n"
        "/reject_agent <user_id> - رفض مندوب\n"
        "/list_orders - عرض جميع الطلبات\n"
        "/cancel_order <order_id> - إلغاء طلب\n"
        "/help - إظهار الأوامر"
    )
    await update.message.reply_text(text)

async def list_pending_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT user_id, full_name, governorate, area, id_photo_url FROM agents WHERE is_verified=FALSE")
        rows = cur.fetchall()
        conn.close()

        if not rows:
            await update.message.reply_text("لا توجد مناديب في انتظار المراجعة.")
            return

        for user_id, full_name, gov, area, photo_url in rows:
            text = f"مندوب: {full_name}\nمحافظة: {gov}\nحي: {area}\nUser ID: {user_id}"
            keyboard = [
                [
                    InlineKeyboardButton("✅ موافقة", callback_data=f"approve_{user_id}"),
                    InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user_id}")
                ]
            ]
            await update.message.reply_photo(photo=photo_url, caption=text, reply_markup=InlineKeyboardMarkup(keyboard))

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ حدث خطأ أثناء جلب المناديب.")

async def approve_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return

    data = query.data
    if not data.startswith("approve_"):
        return

    user_id = int(data.split("_")[1])

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE agents SET is_verified=TRUE WHERE user_id=%s", (user_id,))
        conn.commit()
        conn.close()
        await query.edit_message_caption("✅ تم الموافقة على المندوب.")
    except Exception as e:
        logging.error(e)
        await query.message.reply_text("❌ حدث خطأ أثناء الموافقة.")

async def reject_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return

    data = query.data
    if not data.startswith("reject_"):
        return

    user_id = int(data.split("_")[1])

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM agents WHERE user_id=%s", (user_id,))
        conn.commit()
        conn.close()
        await query.edit_message_caption("❌ تم رفض وحذف المندوب.")
    except Exception as e:
        logging.error(e)
        await query.message.reply_text("❌ حدث خطأ أثناء الرفض.")

async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, user_id, governorate, area, address, phone, text, status FROM orders ORDER BY id DESC")
        rows = cur.fetchall()
        conn.close()

        if not rows:
            await update.message.reply_text("لا توجد طلبات حالياً.")
            return

        text = "الطلبات الحالية:\n"
        for oid, uid, gov, area, address, phone, txt, status in rows:
            text += f"\n#{oid} - {status}\nالمستخدم: {uid}\nالمحافظة: {gov}\nالحي: {area}\nالعنوان: {address}\nرقم الهاتف: {phone}\nالتفاصيل: {txt}\n"

        await update.message.reply_text(text)

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ حدث خطأ أثناء جلب الطلبات.")

async def admin_cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية.")

    if len(context.args) != 1 or not context.args[0].isdigit():
        return await update.message.reply_text("❌ استخدم: /cancel_order <رقم_الطلب>")

    oid = int(context.args[0])

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT status FROM orders WHERE id=%s", (oid,))
        row = cur.fetchone()
        if not row:
            await update.message.reply_text(f"❌ لا يوجد طلب بالرقم {oid}.")
            conn.close()
            return

        cur.execute("UPDATE orders SET status='ملغى' WHERE id=%s", (oid,))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ تم إلغاء الطلب رقم {oid} بنجاح.")

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ حدث خطأ أثناء إلغاء الطلب.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("help", admin_help))
    app.add_handler(CommandHandler("list_pending_agents", list_pending_agents))
    app.add_handler(CallbackQueryHandler(approve_agent, pattern=r"^approve_"))
    app.add_handler(CallbackQueryHandler(reject_agent, pattern=r"^reject_"))
    app.add_handler(CommandHandler("list_orders", list_orders))
    app.add_handler(CommandHandler("cancel_order", admin_cancel_order))

    app.run_polling()
