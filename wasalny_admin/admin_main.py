import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, filters

ADMIN_ID = 1044357384  # استبدل برقمك الخاص

DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "مرحباً في لوحة الإدارة!\n\n"
        "الأوامر:\n"
        "/pending_agents - عرض المناديب في انتظار المراجعة\n"
        "/approve_agent <user_id> - الموافقة على مندوب\n"
        "/reject_agent <user_id> - رفض مندوب\n"
        "/orders - عرض الطلبات\n"
        "/delete_order <order_id> - حذف طلب\n"
        "/help - عرض الأوامر"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "أوامر الإدارة:\n"
        "/pending_agents - عرض المناديب بانتظار المراجعة\n"
        "/approve_agent <user_id> - الموافقة على مندوب\n"
        "/reject_agent <user_id> - رفض مندوب\n"
        "/orders - عرض الطلبات\n"
        "/delete_order <order_id> - حذف طلب\n"
    )

async def pending_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT user_id, full_name, governorate, area, id_photo_url FROM agents WHERE is_verified=FALSE")
        rows = cur.fetchall()
        conn.close()
        if not rows:
            await update.message.reply_text("لا يوجد مناديب بانتظار المراجعة.")
            return
        for row in rows:
            user_id, full_name, gov, area, photo_url = row
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ موافقة", callback_data=f"approve_{user_id}"),
                    InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user_id}")
                ]
            ])
            text = (
                f"مندوب جديد بانتظار المراجعة:\n"
                f"الاسم: {full_name}\n"
                f"المحافظة: {gov}\n"
                f"الحي: {area}\n"
                f"صورة البطاقة:\n{photo_url}"
            )
            await update.message.reply_photo(photo=photo_url, caption=text, reply_markup=kb)
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ خطأ في جلب المناديب.")

async def approve_reject_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    data = q.data
    parts = data.split("_")
    if len(parts) != 2:
        await q.message.reply_text("❌ خطأ في البيانات.")
        return
    action, user_id_str = parts
    user_id = int(user_id_str)
    try:
        conn = get_conn()
        cur = conn.cursor()
        if action == "approve":
            cur.execute("UPDATE agents SET is_verified=TRUE WHERE user_id=%s", (user_id,))
            conn.commit()
            await q.message.reply_text(f"✅ تم الموافقة على المندوب {user_id}.")
        elif action == "reject":
            cur.execute("DELETE FROM agents WHERE user_id=%s", (user_id,))
            conn.commit()
            await q.message.reply_text(f"❌ تم رفض وحذف المندوب {user_id}.")
        conn.close()
    except Exception as e:
        logging.error(e)
        await q.message.reply_text("❌ خطأ في تحديث حالة المندوب.")

async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""SELECT id, user_id, governorate, area, address, phone, text, status, selected_agent_id FROM orders ORDER BY id DESC LIMIT 20""")
        rows = cur.fetchall()
        conn.close()
        if not rows:
            await update.message.reply_text("لا يوجد طلبات.")
            return
        for row in rows:
            oid, uid, gov, area, addr, phone, text, status, agent_id = row
            msg = (
                f"طلب #{oid}\n"
                f"المستخدم: {uid}\n"
                f"المحافظة: {gov}\n"
                f"الحي: {area}\n"
                f"العنوان: {addr}\n"
                f"الهاتف: {phone}\n"
                f"التفاصيل: {text}\n"
                f"الحالة: {status}\n"
                f"المندوب: {agent_id if agent_id else 'غير معين'}"
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ حذف الطلب", callback_data=f"delete_order_{oid}")]])
            await update.message.reply_text(msg, reply_markup=kb)
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ خطأ في جلب الطلبات.")

async def delete_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    data = q.data
    parts = data.split("_")
    if len(parts) != 3:
        await q.message.reply_text("❌ خطأ في بيانات الحذف.")
        return
    _, _, oid_str = parts
    oid = int(oid_str)
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM orders WHERE id=%s", (oid,))
        cur.execute("DELETE FROM offers WHERE order_id=%s", (oid,))
        cur.execute("DELETE FROM ratings WHERE order_id=%s", (oid,))
        conn.commit()
        conn.close()
        await q.message.reply_text(f"✅ تم حذف الطلب رقم {oid}.")
    except Exception as e:
        logging.error(e)
        await q.message.reply_text("❌ خطأ في حذف الطلب.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(os.getenv("ADMIN_TOKEN")).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("pending_agents", pending_agents))
    app.add_handler(CallbackQueryHandler(approve_reject_agent, pattern="^(approve_|reject_).+"))
    app.add_handler(CommandHandler("orders", list_orders))
    app.add_handler(CallbackQueryHandler(delete_order, pattern="^delete_order_"))

    app.run_polling()
