import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

TOKEN = os.getenv("BOT_TOKEN_ADMIN")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    # ممكن تضيف فلتر على admin_id لو عاوز بس دلوقتي مش عامل صلاحيات
    await update.message.reply_text(
        "أهلاً بك في لوحة الإدارة.\n"
        "استخدم الأوامر:\n"
        "/orders - عرض الطلبات الأخيرة\n"
        "/agents - عرض المندوبين المعلقين للمراجعة"
    )

# عرض الطلبات
async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, user_id, governorate, area, text, status FROM orders
            ORDER BY id DESC LIMIT 20
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            await update.message.reply_text("لا توجد طلبات حالياً.")
            return

        msg = "آخر 20 طلب:\n\n"
        for row in rows:
            msg += f"🆔 #{row[0]} - مستخدم: {row[1]}\n"
            msg += f"📍 {row[2]} - {row[3]}\n"
            msg += f"📦 {row[4]}\n"
            msg += f"الحالة: {row[5]}\n\n"

        await update.message.reply_text(msg)
    except Exception as e:
        logging.error(f"❌ خطأ في جلب الطلبات: {e}")
        await update.message.reply_text("❌ خطأ في جلب الطلبات.")

# عرض المندوبين المعلقين
async def agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, full_name, governorate, area, id_photo_file_id, is_verified
            FROM agents
            WHERE is_verified = FALSE
            ORDER BY user_id
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            await update.message.reply_text("لا يوجد مندوبين للمراجعة حالياً.")
            return

        # عرض أول مندوب مع صورة البطاقة وأزرار قبول / رفض
        first = rows[0]
        user_id, full_name, governorate, area, photo_file_id, is_verified = first

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ قبول", callback_data=f"accept_{user_id}"),
                InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user_id}")
            ]
        ])

        msg = (
            f"مندوب جديد للمراجعة:\n\n"
            f"🆔 UserID: {user_id}\n"
            f"👤 الاسم: {full_name}\n"
            f"📍 {governorate} - {area}\n"
            f"✅ حالة التحقق: {is_verified}\n"
            f"📸 صورة البطاقة مرفقة أدناه."
        )

        await update.message.reply_photo(photo=photo_file_id, caption=msg, reply_markup=keyboard)
    except Exception as e:
        logging.error(f"❌ خطأ في جلب المندوبين: {e}")
        await update.message.reply_text("❌ خطأ في جلب المندوبين.")

# التعامل مع أزرار قبول/رفض
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("accept_"):
        user_id = int(data.split("_")[1])
        await set_agent_verification(user_id, True)
        await query.edit_message_caption(caption=f"✅ تم قبول المندوب {user_id}.")
        await query.message.reply_text(f"تم قبول المندوب {user_id}.")
    elif data.startswith("reject_"):
        user_id = int(data.split("_")[1])
        await set_agent_verification(user_id, False, rejected=True)
        await query.edit_message_caption(caption=f"❌ تم رفض المندوب {user_id}.")
        await query.message.reply_text(f"تم رفض المندوب {user_id}.")

async def set_agent_verification(user_id: int, verified: bool, rejected=False):
    try:
        conn = get_conn()
        cur = conn.cursor()
        if rejected:
            # حذف المندوب المرفوض
            cur.execute("DELETE FROM agents WHERE user_id = %s", (user_id,))
        else:
            cur.execute("UPDATE agents SET is_verified = %s WHERE user_id = %s", (verified, user_id))
        conn.commit()
        cur.close()
        conn.close()
        logging.info(f"تم تحديث حالة التحقق للمندوب {user_id} إلى {verified}")
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث حالة التحقق للمندوب {user_id}: {e}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("orders", orders))
    app.add_handler(CommandHandler("agents", agents))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.run_polling()
