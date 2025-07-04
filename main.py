import logging
import os
import psycopg2
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
logging.basicConfig(level=logging.INFO)

user_states = {}
user_data = {}

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
    text = update.message.text

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
            cursor.execute("INSERT INTO orders (user_id, governorate, text, status) VALUES (%s, %s, %s, %s)",
                           (user_id, governorate, text, "قيد الانتظار"))
            conn.commit()
            cursor.execute("SELECT user_id FROM agents WHERE governorate = %s", (governorate,))
            agents = cursor.fetchall()
            for agent in agents:
                try:
                    await context.bot.send_message(chat_id=agent[0], text=f"📦 طلب جديد في {governorate}:\n{text}\nاضغط للرد بسعر ووقت التوصيل.")
                except:
                    logging.warning(f"⚠️ فشل في إرسال الطلب للمندوب {agent[0]}")
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
                cursor.execute("INSERT INTO agents (user_id, governorate) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (user_id, text))
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
