import os
import logging
import asyncio
from datetime import datetime
from flask import Flask, request

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ================== ENV ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH")

if not all([BOT_TOKEN, ADMIN_CHAT_ID, RENDER_EXTERNAL_URL, WEBHOOK_PATH]):
    raise RuntimeError("❌ Не заданы переменные окружения")

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

# ================== LOGGING ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bot")

# ================== STATES ==================
FIO, BIRTHDATE, INN, DELIVERY, EMAIL, RECEIPTS = range(6)

# ================== FLASK ==================
flask_app = Flask(__name__)

# ================== BOT ==================
application = Application.builder().token(BOT_TOKEN).build()


# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("START from %s", update.effective_user.id)
    context.user_data.clear()
    await update.message.reply_text("Введите ФИО:")
    return FIO


async def fio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fio"] = update.message.text.strip()
    await update.message.reply_text("Введите дату рождения (ДД.ММ.ГГГГ):")
    return BIRTHDATE


async def birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        datetime.strptime(update.message.text, "%d.%m.%Y")
        context.user_data["birthdate"] = update.message.text
        await update.message.reply_text("Введите ИНН:")
        return INN
    except ValueError:
        await update.message.reply_text("❌ Формат: 31.12.2000")
        return BIRTHDATE


async def inn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["inn"] = update.message.text.strip()
    keyboard = ReplyKeyboardMarkup(
        [["Оригинал на бумаге"], ["На email"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text(
        "Выберите способ получения:",
        reply_markup=keyboard,
    )
    return DELIVERY


async def delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["delivery"] = update.message.text
    if update.message.text == "На email":
        await update.message.reply_text(
            "Введите email:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return EMAIL
    else:
        context.user_data["email"] = "—"
        await update.message.reply_text("Пришлите фото чеков или напишите «Чеков нет»:")
        return RECEIPTS


async def email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["email"] = update.message.text.strip()
    await update.message.reply_text("Пришлите фото чеков или напишите «Чеков нет»:")
    return RECEIPTS


async def receipts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = context.user_data

    data["user_id"] = user.id
    data["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    text = (
        "📄 *Новая заявка*\n\n"
        f"👤 ФИО: {data['fio']}\n"
        f"🎂 ДР: {data['birthdate']}\n"
        f"🧾 ИНН: {data['inn']}\n"
        f"📦 Получение: {data['delivery']}\n"
        f"📧 Email: {data.get('email','—')}\n"
        f"👤 User ID: {data['user_id']}\n"
        f"🕒 Время: {data['time']}"
    )

    await application.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=text,
        parse_mode="Markdown",
    )

    if update.message.photo:
        for photo in update.message.photo:
            await application.bot.send_photo(
                chat_id=ADMIN_CHAT_ID,
                photo=photo.file_id,
            )
        await application.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text="🧾 Чеки: фото получены",
        )
    else:
        await application.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"🧾 Чеки: {update.message.text}",
        )

    await update.message.reply_text(
        "✅ Спасибо! Справка будет оформлена в течение 30 дней."
    )
    return ConversationHandler.END


# ================== CONVERSATION ==================
application.add_handler(
    ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, fio)],
            BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, birthdate)],
            INN: [MessageHandler(filters.TEXT & ~filters.COMMAND, inn)],
            DELIVERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, delivery)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email)],
            RECEIPTS: [MessageHandler(filters.TEXT | filters.PHOTO, receipts)],
        },
        fallbacks=[],
    )
)

# ================== WEBHOOK (SYNC) ==================
@flask_app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run(application.process_update(update))
    except Exception:
        logger.exception("Webhook error")
    return "OK"


@flask_app.route("/")
def index():
    return "Bot is running"


# ================== STARTUP ==================
async def set_webhook():
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info("Webhook set to %s", WEBHOOK_URL)


asyncio.run(set_webhook())
