import os
import logging
from datetime import datetime
from flask import Flask, request

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
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
    raise RuntimeError("❌ Не заданы все переменные окружения")

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

# ================== LOGGING ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ================== STATES ==================
(
    FIO,
    BIRTHDATE,
    INN,
    DELIVERY,
    EMAIL,
    RECEIPTS,
) = range(6)

# ================== FLASK ==================
flask_app = Flask(__name__)

# ================== BOT ==================
application = Application.builder().token(BOT_TOKEN).build()


# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Start from user %s", update.effective_user.id)
    context.user_data.clear()
    await update.message.reply_text("Введите ФИО:")
    return FIO


async def fio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fio"] = update.message.text.strip()
    await update.message.reply_text("Введите дату рождения (ДД.ММ.ГГГГ):")
    return BIRTHDATE


async def birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        datetime.strptime(text, "%d.%m.%Y")
        context.user_data["birthdate"] = text
        await update.message.reply_text("Введите ИНН:")
        return INN
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Пример: 31.12.2000")
        return BIRTHDATE


async def inn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["inn"] = update.message.text.strip()
    keyboard = ReplyKeyboardMarkup(
        [["Оригинал на бумаге"], ["На email"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text(
        "Выберите способ получения справки:",
        reply_markup=keyboard,
    )
    return DELIVERY


async def delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    context.user_data["delivery"] = choice

    if choice == "На email":
        await update.message.reply_text(
            "Введите email:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return EMAIL
    else:
        context.user_data["email"] = "—"
        await update.message.reply_text(
            "Пришлите фото чеков или напишите «Чеков нет»:",
            reply_markup=ReplyKeyboardRemove(),
        )
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

    text_report = (
        "📄 *Новая заявка на справку*\n\n"
        f"👤 ФИО: {data['fio']}\n"
        f"🎂 Дата рождения: {data['birthdate']}\n"
        f"🧾 ИНН: {data['inn']}\n"
        f"📦 Получение: {data['delivery']}\n"
        f"📧 Email: {data.get('email','—')}\n"
        f"👤 User ID: {data['user_id']}\n"
        f"🕒 Время: {data['time']}"
    )

    try:
        await application.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=text_report,
            parse_mode="Markdown",
        )

        if update.message.photo:
            for photo in update.message.photo:
                await application.bot.send_photo(
                    chat_id=ADMIN_CHAT_ID,
                    photo=photo.file_id,
                )
            status = "Фото чеков получены"
        else:
            status = update.message.text

        await application.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"🧾 Чеки: {status}",
        )

    except Exception:
        logger.exception("Ошибка отправки админу")

    await update.message.reply_text(
        "✅ Спасибо! Справка будет оформлена в течение 30 дней."
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END


# ================== CONVERSATION ==================
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, fio)],
        BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, birthdate)],
        INN: [MessageHandler(filters.TEXT & ~filters.COMMAND, inn)],
        DELIVERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, delivery)],
        EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email)],
        RECEIPTS: [
            MessageHandler(filters.PHOTO | filters.TEXT, receipts)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

application.add_handler(conv_handler)

# ================== WEBHOOK ==================
@flask_app.post(WEBHOOK_PATH)
async def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
    except Exception:
        logger.exception("Webhook error")
    return "OK"


@flask_app.route("/")
def index():
    return "Bot is running"


# ================== STARTUP ==================
async def startup():
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info("Webhook set: %s", WEBHOOK_URL)


application.post_init = startup

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=10000)
