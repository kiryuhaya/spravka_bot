import os
import logging
from datetime import datetime
from collections import defaultdict

# Словарь для накопления фото
pending_photos = defaultdict(list)

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

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "1660333700"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан")

# ================== LOGGING ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bot")

# ================== STATES ==================
FIO, BIRTHDATE, INN, DELIVERY, EMAIL, RECEIPTS = range(6)

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
        await update.message.reply_text("❌ Формат даты: 31.12.2000")
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

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отдельный обработчик для всех приходящих фото"""
    user_id = update.effective_user.id

    if update.message.photo:
        for photo in update.message.photo:
            pending_photos[user_id].append(photo.file_id)
            await context.bot.send_photo(ADMIN_CHAT_ID, photo.file_id)

    # === Завершаем разговор после получения фото ===
    await update.message.reply_text(
        "✅ Фото получены! Справка будет оформлена в течение 30 дней."
    )

    # Чистим список фото
    pending_photos.pop(user_id, None)

    return ConversationHandler.END


async def delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["delivery"] = update.message.text

    if update.message.text == "На email":
        await update.message.reply_text(
            "Введите email:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return EMAIL

    context.user_data["email"] = "—"
    await update.message.reply_text(
        "Пришлите фото чеков или напишите «Чеков нет» и год справки (например: Чеков нет 2023):",  # ИЗМЕНЕНО ЗДЕСЬ
        reply_markup=ReplyKeyboardRemove(),
    )
    return RECEIPTS


async def email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["email"] = update.message.text.strip()
    await update.message.reply_text(
        "Пришлите фото чеков или напишите «Чеков нет» и год справки (например: Чеков нет 2023):"  # ИЗМЕНЕНО ЗДЕСЬ
    )
    return RECEIPTS


async def receipts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = context.user_data

    # Формируем текст заявки
    text = (
        "📄 *Новая заявка на справку*\n\n"
        f"👤 ФИО: {data['fio']}\n"
        f"🎂 Дата рождения: {data['birthdate']}\n"
        f"🧾 ИНН: {data['inn']}\n"
        f"📦 Получение: {data['delivery']}\n"
        f"📧 Email: {data.get('email','—')}\n"
        f"👤 User ID: {user.id}\n"
        f"🕒 Время: {datetime.now():%Y-%m-%d %H:%M:%S}"
    )

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=text,
        parse_mode="Markdown",
    )

    # === Работа с фото ===
    photo_list = pending_photos[user.id]

    if photo_list:
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"🧾 Получено {len(photo_list)} фото чека(ов)"
        )
    else:
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"🧾 Чеки: {update.message.text}"
        )

    # Чистим список фото для этого пользователя
    pending_photos.pop(user.id, None)

    await update.message.reply_text(
        "✅ Спасибо! Справка будет оформлена в течение 30 дней."
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Операция отменена.")
    return ConversationHandler.END


# ================== MAIN ==================
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
                FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, fio)],
                BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, birthdate)],
                INN: [MessageHandler(filters.TEXT & ~filters.COMMAND, inn)],
                DELIVERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, delivery)],
                EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email)],
                RECEIPTS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, receipts),   
                    MessageHandler(filters.PHOTO, handle_photo),                 
                ],
            },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv)

    logger.info("Bot started (polling)")
    application.run_polling()


if __name__ == "__main__":
    main()
