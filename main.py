import logging
import os
import re
import psycopg2
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)

user_states = {}
user_data = {}
# لربط الطلب الحالي اللي المندوب بيرد عليه
agent_current_order = {}

def create_tables():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        governorate TEXT,
        text TEXT,
        status TEXT DEFAULT 'قيد الانتظار'
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agents (
        id SERIAL PRIMARY KEY,
        user_id BIGINT UNIQUE,
        governorate TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS offers (
        id SERIAL PRIMARY KEY,
        order_id INT REFERENCES orders(id),
        agent_id BIGINT,
        price TEXT,
        eta TEXT,
        status TEXT DEFAULT 'قيد الانتظار'
    )""")
    conn.commit()
    cursor.close()
    conn.close()

governorates = ["القاهرة", "الجيزة", "الإسكندرية", "الدقهلية", "الشرقية", "المنوفية"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]]
    await update.message.reply_text("أهلاً بيك! اختار دورك:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # إذا المندوب في حالة انتظار رد عرض
    if user_states.get(user_id) == "awaiting_offer":
        # نتحقق من الرد هل فيه سعر ووقت بصيغة صحيحة: مثلا "50 جنيه 30 دقيقة"
        pattern = r"(\d+(\.\d+)?)\s*(جنيه|EGP)?\s+(\d+)\s*(دقيقة|دقايق|دقائق)"
        match = re.search(pattern, text)
        if not match:
            await update.message.reply_text("❌ الرد غير صحيح، اكتب السعر والوقت مثلاً: 50 جنيه 30 دقيقة")
            return

        price = match.group(1)
        eta = match.group(4) + " دقيقة"

        order_id = agent_current_order.get(user_id)
        if not order_id:
            await update.message.reply_text("❌ ما فيش طلب مرتبط حالياً للعرض.")
            user_states[user_id] = None
            return

        try:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            # نحفظ العرض في جدول offers
            cursor.execute(
                "INSERT INTO offers (order_id, agent_id, price, eta, status) VALUES (%s, %s, %s, %s, %s)",
                (order_id, user_id, price, eta, "قيد الانتظار")
            )
            conn.commit()
            cursor.close()
            conn.close()
            await update.message.reply_text(f"✅ تم إرسال العرض: السعر {price} جنيه، الوقت {eta}")
            user_states[user_id] = None
            agent_current_order.pop(user_id, None)
        except Exception as e:
            logging.error(f"❌ خطأ في حفظ العرض: {e}")
            await update.message.reply_text("❌ حدث خطأ أثناء حفظ العرض.")
        return

    if text == "🚶‍♂️ مستخدم":
        user_states[user_id] = "awaiting_user_governorate"
        await update.message.reply_text("اختار محافظتك:", reply_markup=ReplyKeyboardMarkup([[g] for g in governorates], resize_keyboard=True))
        return

    if user_states.get(user_id) == "awaiting_user_governorate":
        if text in governorates:
            user_data[user_id] = {"governorate": text}
            user_states[user_id] = "awaiting_order_text"
            await update.message.reply_text("اكتب طلبك بالتفصيل:")
        else:
            await update.message.reply_text("❌ اختار محافظة من القائمة.")
        return

    if user_states.get(user_id) == "awaiting_order_text":
        governorate = user_data[user_id]["governorate"]
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO orders (user_id, governorate, text, status) VALUES (%s, %s, %s, %s) RETURNING id",
                           (user_id, governorate, text, "قيد الانتظار"))
            order_id = cursor.fetchone()[0]
            conn.commit()

            # نجيب المناديب في نفس المحافظة
            cursor.execute("SELECT user_id FROM agents WHERE governorate = %s", (governorate,))
            agents = cursor.fetchall()

            for agent in agents:
                aid = agent[0]
                # حفظ حالة انتظار عرض لكل مندوب (الطلب اللي لازم يرد عليه)
                agent_current_order[aid] = order_id
                try:
                    await context.bot.send_message(chat_id=aid, text=f"📦 طلب جديد في {governorate}:\n{text}\n\n*رد بالعرض بالسعر والوقت* مثل:\n50 جنيه 30 دقيقة")
                except Exception as e:
                    logging.warning(f"⚠️ فشل في إرسال الطلب للمندوب {aid}: {e}")

            cursor.close()
            conn.close()
            await update.message.reply_text("✅ تم استلام طلبك، هيتم إرسال العروض ليك من المناديب قريباً.")
        except Exception as e:
            logging.error(f"❌ خطأ في حفظ الطلب: {e}")
            await update.message.reply_text("❌ حصل مشكلة أثناء حفظ الطلب.")
        user_states[user_id] = None
        return

    if text == "🚚 مندوب":
        user_states[user_id] = "awaiting_agent_governorate"
        await update.message.reply_text("اختار محافظتك كمندوب:", reply_markup=ReplyKeyboardMarkup([[g] for g in governorates], resize_keyboard=True))
        return

    if user_states.get(user_id) == "awaiting_agent_governorate":
        if text in governorates:
            try:
                conn = psycopg2.connect(DATABASE_URL)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO agents (user_id, governorate) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET governorate = EXCLUDED.governorate",
                               (user_id, text))
                conn.commit()
                cursor.close()
                conn.close()
                await update.message.reply_text("✅ تم تسجيلك كمندوب. هيتم إرسال الطلبات من محافظتك تلقائيًا.")
            except Exception as e:
                logging.error(f"❌ فشل تسجيل المندوب: {e}")
                await update.message.reply_text("❌ حصل خطأ أثناء تسجيلك كمندوب.")
            user_states[user_id] = None
        else:
            await update.message.reply_text("❌ اختار محافظة من القائمة.")
        return

    await update.message.reply_text("من فضلك ابدأ بـ /start")

def main():
    create_tables()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logging.info("📦 بوت المستخدم والمناديب شغال...")
    app.run_polling()

if __name__ == "__main__":
    main()
