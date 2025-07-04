import logging
import sqlite3
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler
)

TOKEN = "8119170278:AAGfqFrfes_0g-EmbBBk2K6e6DjQflwlBg0"

logging.basicConfig(level=logging.INFO)

user_states = {}
user_roles = {}
pending_orders = {}

def init_db():
    conn = sqlite3.connect("wasalny/data.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            status TEXT DEFAULT 'بانتظار عرض',
            selected_offer INTEGER,
            rating INTEGER
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            courier_id INTEGER,
            price TEXT,
            eta TEXT
        )
    ''')
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("🚶‍♂️ مستخدم"), KeyboardButton("🚚 مندوب")]
    ]
    await update.message.reply_text(
        "أهلاً بيك في وصّلني! اختار نوع الاستخدام:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # اختيار مستخدم أو مندوب
    if text == "🚶‍♂️ مستخدم":
        user_roles[user_id] = "user"
        user_states[user_id] = "awaiting_order"
        await update.message.reply_text("📝 اكتب طلبك بالتفصيل (مثال: 1 كيلو طماطم، 2 رغيف)...")
        return

    elif text == "🚚 مندوب":
        user_roles[user_id] = "courier"
        await update.message.reply_text("✅ تم تسجيلك كمندوب! هتوصلك إشعارات لما يوصل طلب.")
        return

    # المستخدم كتب الطلب
    if user_roles.get(user_id) == "user" and user_states.get(user_id) == "awaiting_order":
        order_text = text
        conn = sqlite3.connect("wasalny/data.db")
        c = conn.cursor()
        c.execute("INSERT INTO orders (user_id, text) VALUES (?, ?)", (user_id, order_text))
        order_id = c.lastrowid
        conn.commit()
        conn.close()

        user_states[user_id] = None
        await update.message.reply_text(f"✅ استلمنا طلبك: {order_text}\n📡 جاري إرسال الطلب للمناديب...")

        # إرسال للمناديب
        for uid, role in user_roles.items():
            if role == "courier":
                await context.bot.send_message(
                    uid,
                    f"📦 طلب جديد من مستخدم:\n\n{order_text}",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("أرسل عرضك", callback_data=f"offer_{order_id}")
                    ]])
                )
        return

    # تقييم بعد التنفيذ
    if user_states.get(user_id, "").startswith("rate_"):
        try:
            rating = int(text)
            if 1 <= rating <= 5:
                order_id = int(user_states[user_id].split("_")[1])
                conn = sqlite3.connect("wasalny/data.db")
                c = conn.cursor()
                c.execute("UPDATE orders SET rating = ?, status = 'تم التوصيل' WHERE id = ?", (rating, order_id))
                conn.commit()
                conn.close()
                await update.message.reply_text("🙏 شكرًا لتقييمك!")
                user_states[user_id] = None
            else:
                await update.message.reply_text("❗ من فضلك اختر تقييم من 1 إلى 5.")
        except:
            await update.message.reply_text("❗ من فضلك اكتب رقم صحيح من 1 إلى 5.")
        return

    # المندوب بيرد بعرض بعد الضغط على "أرسل عرضك"
    if user_states.get(user_id, "").startswith("sending_offer_"):
        order_id = int(user_states[user_id].split("_")[2])
        try:
            price, eta = text.split("+")
        except:
            await update.message.reply_text("❗ اكتب العرض بالشكل: السعر + الوقت (مثال: 30 جنيه + 20 دقيقة)")
            return

        conn = sqlite3.connect("wasalny/data.db")
        c = conn.cursor()
        c.execute("INSERT INTO offers (order_id, courier_id, price, eta) VALUES (?, ?, ?, ?)",
                  (order_id, user_id, price.strip(), eta.strip()))
        conn.commit()

        # نجيب صاحب الطلب
        c.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,))
        user_row = c.fetchone()
        conn.close()

        if user_row:
            user = user_row[0]
            await context.bot.send_message(
                user,
                f"📨 عرض جديد لطلبك:\nالسعر: {price.strip()}\nالوقت المتوقع: {eta.strip()}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("اختيار هذا العرض", callback_data=f"choose_{order_id}_{user_id}")
                ]])
            )
        await update.message.reply_text("✅ تم إرسال عرضك للمستخدم.")
        user_states[user_id] = None
        return

    await update.message.reply_text("❗ من فضلك ابدأ بـ /start واختار دورك.")

async def handle_offer_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    courier_id = query.from_user.id
    order_id = int(query.data.split("_")[1])
    user_states[courier_id] = f"sending_offer_{order_id}"
    await query.message.reply_text("✍️ اكتب عرضك (السعر + الوقت المتوقع)")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id, courier_id = map(int, query.data.split("_")[1:])
    conn = sqlite3.connect("wasalny/data.db")
    c = conn.cursor()
    c.execute("UPDATE orders SET selected_offer = ?, status = 'تم اختيار المندوب' WHERE id = ?", (courier_id, order_id))
    conn.commit()
    conn.close()

    await query.message.reply_text("✅ تم اختيار هذا العرض.")
    await context.bot.send_message(courier_id, f"🚀 تم اختيارك لتوصيل الطلب رقم {order_id}.")
    await context.bot.send_message(query.from_user.id, "🧾 من فضلك قيم الخدمة من 1 إلى 5 بعد الاستلام.")
    user_states[query.from_user.id] = f"rate_{order_id}"

# ======= Run bot ========
init_db()
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(handle_offer_button, pattern="^offer_"))
app.add_handler(CallbackQueryHandler(handle_choice, pattern="^choose_"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

if __name__ == "__main__":
    app.run_polling()
