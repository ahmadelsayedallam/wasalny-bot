import logging
import os
import psycopg2
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters

TOKEN = os.getenv("BOT_TOKEN_USER")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)
user_states = {}
agent_current_order = {}
agent_offer_data = {}  # {agent_id: {"order_id": ..., "price": ...}}

GOVS = ["القاهرة", "الجيزة", "الإسكندرية"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]]
    await update.message.reply_text("أهلاً بيك! اختار دورك:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text == "🚶‍♂️ مستخدم":
        user_states[user_id] = "awaiting_governorate"
        await update.message.reply_text("📍 من فضلك اختار محافظتك:", reply_markup=ReplyKeyboardMarkup([[g] for g in GOVS], resize_keyboard=True))
        return

    if user_states.get(user_id) == "awaiting_governorate" and text in GOVS:
        user_states[user_id] = {"state": "awaiting_order", "gov": text}
        await update.message.reply_text("📝 اكتب تفاصيل طلبك:")
        return

    if isinstance(user_states.get(user_id), dict) and user_states[user_id]["state"] == "awaiting_order":
        order_text = text
        governorate = user_states[user_id]["gov"]
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO orders (user_id, governorate, text, status) VALUES (%s, %s, %s, %s) RETURNING id",
                           (user_id, governorate, order_text, "قيد الانتظار"))
            order_id = cursor.fetchone()[0]
            conn.commit()
            conn.close()
            logging.info(f"✅ تم حفظ الطلب: {order_id} للمستخدم {user_id}")

            await update.message.reply_text("✅ تم استلام طلبك. 📢 هنرسله للمناديب دلوقتي...")

            # ابعت الطلب لكل المناديب في نفس المحافظة
            for agent_id, agent_gov in context.bot_data.get("agents", {}).items():
                if agent_gov == governorate:
                    await context.bot.send_message(
                        chat_id=agent_id,
                        text=f"📦 طلب جديد من {governorate}:\n{order_text}",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("تقديم عرض", callback_data=f"offer_price_{order_id}")]
                        ])
                    )

        except Exception as e:
            logging.error(f"❌ فشل حفظ الطلب: {e}")
            await update.message.reply_text("❌ حصل خطأ أثناء حفظ طلبك.")

        user_states[user_id] = None
        return

    if text == "🚚 مندوب":
        user_states[user_id] = "awaiting_agent_gov"
        await update.message.reply_text("📍 اختار محافظتك:", reply_markup=ReplyKeyboardMarkup([[g] for g in GOVS], resize_keyboard=True))
        return

    if user_states.get(user_id) == "awaiting_agent_gov" and text in GOVS:
        context.bot_data.setdefault("agents", {})[user_id] = text
        user_states[user_id] = None
        await update.message.reply_text("✅ تم تسجيلك كمندوب! هيوصلك الطلبات اللي في محافظتك.")
        return

async def handle_offer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    step = data[1]

    if step == "price":
        order_id = int(data[2])
        agent_current_order[query.from_user.id] = order_id
        prices = [30, 40, 50, 60]
        buttons = [[InlineKeyboardButton(f"{p} جنيه", callback_data=f"offer_eta_price_{p}")] for p in prices]
        await query.message.reply_text("💰 اختار السعر:", reply_markup=InlineKeyboardMarkup(buttons))

    elif step == "eta":
        price = int(data[3])
        agent_id = query.from_user.id
        order_id = agent_current_order.get(agent_id)
        agent_offer_data[agent_id] = {"order_id": order_id, "price": price}

        etas = [10, 20, 30]
        buttons = [[InlineKeyboardButton(f"{e} دقيقة", callback_data=f"submit_offer_{e}")] for e in etas]
        await query.message.reply_text("⏱ اختار وقت التوصيل:", reply_markup=InlineKeyboardMarkup(buttons))

    elif step == "offer":
        eta = int(data[2])
        agent_id = query.from_user.id
        data = agent_offer_data.get(agent_id)

        if not data:
            await query.message.reply_text("❌ لم يتم اختيار السعر.")
            return

        order_id = data["order_id"]
        price = data["price"]

        try:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO offers (order_id, agent_id, price, eta, status) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (order_id, agent_id, price, eta, "قيد الانتظار")
            )
            offer_id = cursor.fetchone()[0]
            cursor.execute("SELECT user_id FROM orders WHERE id = %s", (order_id,))
            user_id = cursor.fetchone()[0]
            conn.commit()
            conn.close()

            await query.message.reply_text("✅ تم إرسال العرض للمستخدم.")
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📬 عرض جديد لطلبك:\n💰 السعر: {price} جنيه\n⏱ الوقت: {eta} دقيقة",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ موافق على العرض", callback_data=f"accept_offer_{offer_id}_{order_id}")]
                ])
            )

        except Exception as e:
            logging.error(f"❌ خطأ في حفظ العرض: {e}")
            await query.message.reply_text("❌ حصل خطأ أثناء إرسال العرض.")

async def accept_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    offer_id, order_id = map(int, query.data.split("_")[2:])

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # اختيار العرض
        cursor.execute("UPDATE offers SET status = 'تم الاختيار' WHERE id = %s", (offer_id,))
        # رفض باقي العروض
        cursor.execute("UPDATE offers SET status = 'مرفوض' WHERE order_id = %s AND id != %s", (order_id, offer_id))
        # تحديث حالة الطلب
        cursor.execute("UPDATE orders SET status = 'قيد التنفيذ' WHERE id = %s", (order_id,))
        conn.commit()
        conn.close()

        await query.message.reply_text("✅ تم قبول العرض، وجاري تنفيذ الطلب 🚚")

    except Exception as e:
        logging.error(f"❌ خطأ في تأكيد العرض: {e}")
        await query.message.reply_text("❌ حصل خطأ أثناء تأكيد العرض.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_offer_callback, pattern=r"^offer_price_\d+$"))
    app.add_handler(CallbackQueryHandler(handle_offer_callback, pattern=r"^offer_eta_price_\d+$"))
    app.add_handler(CallbackQueryHandler(handle_offer_callback, pattern=r"^submit_offer_\d+$"))
    app.add_handler(CallbackQueryHandler(accept_offer, pattern=r"^accept_offer_\d+_\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logging.info("🚀 البوت شغال...")
    app.run_polling()

if __name__ == "__main__":
    main()
