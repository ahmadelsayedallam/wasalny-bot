import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

TOKEN = os.getenv("BOT_TOKEN_ADMIN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1044357384"))

logging.basicConfig(level=logging.INFO)
def get_conn(): return psycopg2.connect(DATABASE_URL)

async def show_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية.")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT user_id,full_name,governorate,area,id_photo_url FROM agents WHERE is_verified=FALSE")
    ags=cur.fetchall(); conn.close()
    if not ags:
        return await update.message.reply_text("✅ لا يوجد مناديب للمراجعة.")
    for uid,fn,gov,ar,pu in ags:
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ قبول",callback_data=f"approve_{uid}"),
                                 InlineKeyboardButton("❌ رفض",callback_data=f"reject_{uid}")]])
        cap=f"👤 {fn}\n🏙️ {gov} - {ar}\nID: {uid}"
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=pu, caption=cap, reply_markup=kb)

async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    d=q.data; uid=int(d.split("_")[1])
    apr = d.startswith("approve_")
    conn=get_conn(); cur=conn.cursor()
    if apr:
        cur.execute("UPDATE agents SET is_verified=TRUE WHERE user_id=%s",(uid,))
        await context.bot.send_message(chat_id=uid, text="✅ تم قبولك كمندوب.")
        await q.edit_message_caption(caption="✅ تم قبول المناديب.")
    else:
        cur.execute("DELETE FROM agents WHERE user_id=%s",(uid,))
        await context.bot.send_message(chat_id=uid, text="❌ تم رفضك.")
        await q.edit_message_caption(caption="❌ تم رفض المناديب.")
    conn.commit(); conn.close()

async def show_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID:
        return await update.message.reply_text("❌ ليس لديك صلاحية.")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT id,user_id,governorate,area,text,status FROM orders ORDER BY id DESC LIMIT 10")
    rs=cur.fetchall(); conn.close()
    if not rs:
        return await update.message.reply_text("✅ لا توجد طلبات.")
    for oid,uid,gov,ar,txt,st in rs:
        await update.message.reply_text(f"📦#{oid}👤{uid}🏙️{gov}-{ar}\n📝{txt}\n📌{st}")

if __name__=="__main__":
    app=ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", show_pending))
    app.add_handler(CommandHandler("pending_agents", show_pending))
    app.add_handler(CommandHandler("orders", show_orders))
    app.add_handler(CallbackQueryHandler(handle_review))
    app.run_polling()
