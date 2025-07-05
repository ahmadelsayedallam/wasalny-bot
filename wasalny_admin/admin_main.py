import os
import logging
import psycopg2
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, filters, MessageHandler
)

# ثابت معرف الادمن
ADMIN_ID = 1044357384

DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = (
        "مرحباً بك في لوحة تحكم الإدارة.\n\n"
        "الأوامر المتاحة:\n"
        "/pending_agents - عرض المناديب في انتظار المراجعة\n"
        "/pending_orders - عرض الطلبات المفتوحة\n"
        "/help - عرض هذه الرسالة\n"
    )
    await update.message.reply_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = (
        "الأوامر المتاحة:\n"
        "/pending_agents - عرض المناديب في انتظار المراجعة\n"
        "/pending_orders - عرض الطلبات المفتوحة\n"
        "/help - عرض هذه الرسالة\n"
        "/cancel_order_رقم_الطلب - إلغاء طلب معين\n"
    )
    await update.message.reply_text(text)

# عرض المناديب في انتظار المراجعة (الذين رفعوا صورة البطاقة)
async def pending_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, full_name, governorate, area, id_photo_url FROM agents WHERE is_verified=FALSE")
        agents = cur.fetchall()
        conn.close()

        if not agents:
            await update.message.reply_text("لا يوجد مناديب في انتظار المراجعة.")
            return

        for agent in agents:
            aid, name, gov, area, photo_url = agent
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ قبول", callback_data=f"verify_agent_{aid}"),
                 InlineKeyboardButton("❌ رفض", callback_data=f"reject_agent_{aid}")]
            ])
            text = (
                f"اسم: {name}\n"
                f"محافظة: {gov}\n"
                f"حي: {area}\n"
                f"صورة البطاقة:"
            )
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_url, caption=text, reply_markup=kb)

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("حدث خطأ أثناء جلب بيانات المناديب.")

# التعامل مع موافقة أو رفض المندوب
async def handle_agent_verification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return

    data = query.data
    try:
        if data.startswith("verify_agent_"):
            aid = int(data.split("_")[-1])
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("UPDATE agents SET is_verified=TRUE WHERE id=%s", (aid,))
            conn.commit()
            conn.close()
            await query.edit_message_caption(caption="✅ تم تفعيل المندوب بنجاح.")
        elif data.startswith("reject_agent_"):
            aid = int(data.split("_")[-1])
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM agents WHERE id=%s", (aid,))
            conn.commit()
            conn.close()
            await query.edit_message_caption(caption="❌ تم رفض وحذف طلب المندوب.")
    except Exception as e:
        logging.error(e)
        await query.message.reply_text("حدث خطأ أثناء معالجة الطلب.")

# عرض الطلبات المفتوحة في انتظار اختيار مندوب
async def pending_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, user_id, governorate, area, address, phone, text, status 
            FROM orders WHERE status='قيد الانتظار'
        """)
        orders = cur.fetchall()
        conn.close()

        if not orders:
            await update.message.reply_text("لا يوجد طلبات مفتوحة حالياً.")
            return

        for order in orders:
            oid, user_id, gov, area, address, phone, text, status = order
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ إلغاء الطلب", callback_data=f"cancel_order_{oid}")]
            ])
            msg = (
                f"رقم الطلب: {oid}\n"
                f"المستخدم: {user_id}\n"
                f"المحافظة: {gov}\n"
                f"الحي: {area}\n"
                f"العنوان: {address}\n"
                f"رقم الهاتف: {phone}\n"
                f"التفاصيل: {text}\n"
                f"الحالة: {status}"
            )
            await update.message.reply_text(msg, reply_markup=kb)
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("حدث خطأ أثناء جلب الطلبات.")

# إلغاء طلب من الإدارة
async def handle_cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = update.message.text
    if not text.startswith("/cancel_order_"):
        return
    try:
        oid = int(text.split("_")[-1])
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM orders WHERE id=%s", (oid,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ تم حذف الطلب رقم {oid}.")
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("حدث خطأ أثناء حذف الطلب.")

# التعامل مع أزرار إلغاء الطلب من قائمة الطلبات
async def handle_cancel_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    data = query.data
    if data.startswith("cancel_order_"):
        try:
            oid = int(data.split("_")[-1])
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM orders WHERE id=%s", (oid,))
            conn.commit()
            conn.close()
            await query.edit_message_text(f"❌ تم إلغاء وحذف الطلب رقم {oid}.")
        except Exception as e:
            logging.error(e)
            await query.message.reply_text("حدث خطأ أثناء إلغاء الطلب.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(os.getenv("ADMIN_TOKEN")).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("pending_agents", pending_agents))
    app.add_handler(CommandHandler("pending_orders", pending_orders))

    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^/cancel_order_\d+$"), handle_cancel_order))
    app.add_handler(CallbackQueryHandler(handle_agent_verification, pattern=r"^(verify_agent_|reject_agent_)"))
    app.add_handler(CallbackQueryHandler(handle_cancel_order_callback, pattern=r"^cancel_order_"))

    app.run_polling()
