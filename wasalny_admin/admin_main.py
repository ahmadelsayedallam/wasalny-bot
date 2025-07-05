import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)
from datetime import datetime, timedelta

# إعداد المتغيرات
TOKEN = os.getenv("BOT_TOKEN_ADMIN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1044357384"))

# لوج
logging.basicConfig(level=logging.INFO)

# الاتصال بقاعدة البيانات
def get_conn():
    return psycopg2.connect(DATABASE_URL)

# /start و /help
async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية.")
    
    text = (
        "📋 *أوامر الإدارة المتاحة:*\n\n"
        "🧾 /pending_agents - مراجعة المناديب قيد الانتظار\n"
        "📦 /orders - عرض آخر 10 طلبات (الحالة + المندوب + التقييم)\n"
        "👥 /all_agents - عرض كل المناديب (مفعلين وغير مفعلين)\n"
        "🔍 /search_order <رقم_الطلب> - البحث عن طلب محدد\n"
        "🗑️ /delete_old_orders - حذف الطلبات القديمة\n"
        "🆘 /help - عرض هذه القائمة\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

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

# التعامل مع زر القبول أو الرفض
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
            await context.bot.send_message(chat_id=uid, text="🎉 تم قبولك كمندوب. يمكنك الآن استقبال الطلبات.")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"✅ تم *قبول* المندوب `{uid}`.", parse_mode="Markdown")
        else:
            cur.execute("DELETE FROM agents WHERE user_id=%s", (uid,))
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ تم *رفض* المندوب `{uid}`.", parse_mode="Markdown")
        
        conn.commit()
        conn.close()

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception as e:
            logging.warning(f"⚠️ لم أستطع إزالة الزرار: {e}")

    except Exception as e:
        logging.error(f"❌ حصل خطأ أثناء معالجة الطلب: {e}")
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ حصل خطأ:\n{e}")

# عرض الطلبات
async def show_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية.")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT o.id, o.user_id, o.governorate, o.area, o.text, o.status, o.address, o.phone,
               a.full_name, r.rating
        FROM orders o
        LEFT JOIN agents a ON o.selected_agent_id = a.user_id
        LEFT JOIN ratings r ON o.id = r.order_id
        ORDER BY o.id DESC
        LIMIT 10
    """)
    orders = cur.fetchall()
    conn.close()

    if not orders:
        return await update.message.reply_text("✅ لا توجد طلبات حالياً.")

    for oid, uid, gov, area, txt, status, address, phone, agent_name, rating in orders:
        agent_info = f"\n🚚 المندوب: {agent_name}" if agent_name else ""
        rating_info = f"\n⭐ التقييم: {rating}/5" if rating else ""
        await update.message.reply_text(
            f"📦 *طلب #{oid}*\n👤 المستخدم: `{uid}`\n🏙️ {gov} - {area}\n📍 العنوان: {address}\n📞 {phone}\n📝 الطلب: {txt}\n📌 الحالة: {status}{agent_info}{rating_info}",
            parse_mode="Markdown"
        )

# عرض كل المناديب (مفعلين وغير مفعلين)
async def show_all_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية.")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, full_name, governorate, area, is_verified FROM agents ORDER BY is_verified DESC, full_name")
    agents = cur.fetchall()
    conn.close()

    if not agents:
        return await update.message.reply_text("✅ لا يوجد مناديب مسجلين.")

    lines = []
    for uid, name, gov, area, verified in agents:
        status = "✅ مفعل" if verified else "⏳ قيد المراجعة"
        lines.append(f"👤 {name} (ID: `{uid}`)\n🏙️ {gov} - {area}\nالحالة: {status}\n")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# البحث عن طلب معين بالرقم
async def search_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية.")
    
    if len(context.args) != 1 or not context.args[0].isdigit():
        return await update.message.reply_text("❌ استخدم: /search_order <رقم_الطلب>")

    oid = int(context.args[0])
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT o.id, o.user_id, o.governorate, o.area, o.text, o.status, o.address, o.phone,
               a.full_name, r.rating
        FROM orders o
        LEFT JOIN agents a ON o.selected_agent_id = a.user_id
        LEFT JOIN ratings r ON o.id = r.order_id
        WHERE o.id = %s
    """, (oid,))
    order = cur.fetchone()
    conn.close()

    if not order:
        return await update.message.reply_text(f"❌ لم يتم العثور على طلب بالرقم {oid}.")

    oid, uid, gov, area, txt, status, address, phone, agent_name, rating = order
    agent_info = f"\n🚚 المندوب: {agent_name}" if agent_name else ""
    rating_info = f"\n⭐ التقييم: {rating}/5" if rating else ""
    await update.message.reply_text(
        f"📦 *طلب #{oid}*\n👤 المستخدم: `{uid}`\n🏙️ {gov} - {area}\n📍 العنوان: {address}\n📞 {phone}\n📝 الطلب: {txt}\n📌 الحالة: {status}{agent_info}{rating_info}",
        parse_mode="Markdown"
    )

# حذف الطلبات القديمة التي انتهت أو لم تُنفذ منذ أكثر من 30 يوم
async def delete_old_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية.")
    
    cutoff_date = datetime.now() - timedelta(days=30)
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            DELETE FROM orders
            WHERE (status = 'تم التوصيل' OR status = 'ملغى' OR status = 'لم يتم اختيار مندوب')
              AND created_at < %s
        """, (cutoff_date,))
        deleted = cur.rowcount
        conn.commit()
        await update.message.reply_text(f"🗑️ تم حذف {deleted} طلب قديم.")
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ حدث خطأ أثناء حذف الطلبات القديمة.")
    finally:
        conn.close()

# تشغيل البوت
if __name__ == "__main__":
    print("🚀 تشغيل WasalnyAdminBot مع أوامر إضافية...")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", show_help))
    app.add_handler(CommandHandler("help", show_help))
    app.add_handler(CommandHandler("pending_agents", show_pending))
    app.add_handler(CommandHandler("orders", show_orders))
    app.add_handler(CommandHandler("all_agents", show_all_agents))
    app.add_handler(CommandHandler("search_order", search_order))
    app.add_handler(CommandHandler("delete_old_orders", delete_old_orders))
    app.add_handler(CallbackQueryHandler(handle_review))

    app.run_polling()
