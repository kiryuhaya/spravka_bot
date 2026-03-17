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
    InputMediaPhoto,
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
FIO, BIRTHDATE, INN, DELIVERY, EMAIL, RECEIPTS, MORE_PHOTOS = range(7)

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
        "Пришлите фото чеков или напишите «Чеков нет 2023»:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return RECEIPTS


async def email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["email"] = update.message.text.strip()
    await update.message.reply_text(
        "Пришлите фото чеков или напишите «Чеков нет 2023»:"
    )
    return RECEIPTS


# ======== ФОТО ========
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if update.message.photo:
        photo = update.message.photo[-1]
        pending_photos[user_id].append(photo.file_id)

    keyboard = ReplyKeyboardMarkup(
        [["Да", "Нет"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await update.message.reply_text(
        "Добавить ещё фото?",
        reply_markup=keyboard
    )

    return MORE_PHOTOS


async def more_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    answer = update.message.text.lower()

    if answer in ["да", "yes", "y"]:
        await update.message.reply_text(
            "Пришлите ещё фото:",
            reply_markup=ReplyKeyboardRemove()
        )
        return RECEIPTS

    # === отправляем заявку ===
    user = update.effective_user
    data = context.user_data

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

    photo_list = pending_photos[user_id]

    if photo_list:
        media = [InputMediaPhoto(fid) for fid in photo_list[:10]]
        await context.bot.send_media_group(
            chat_id=ADMIN_CHAT_ID,
            media=media
        )
    else:
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            "🧾 Чеки не были отправлены"
        )

    pending_photos.pop(user_id, None)

    await update.message.reply_text(
        "✅ Фото получены! Справка будет оформлена в течение 30 дней.",
        reply_markup=ReplyKeyboardRemove()
    )

    return ConversationHandler.END

# ======== ТЕКСТ ========
async def receipts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if "чеков нет" in text:
        user = update.effective_user
        data = context.user_data

        msg = (
            "📄 *Новая заявка на справку*\n\n"
            f"👤 ФИО: {data['fio']}\n"
            f"🎂 Дата рождения: {data['birthdate']}\n"
            f"🧾 ИНН: {data['inn']}\n"
            f"📦 Получение: {data['delivery']}\n"
            f"📧 Email: {data.get('email','—')}\n"
            f"🧾 Чеки: {update.message.text}\n"
            f"👤 User ID: {user.id}\n"
            f"🕒 Время: {datetime.now():%Y-%m-%d %H:%M:%S}"
        )

        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=msg,
            parse_mode="Markdown",
        )

        await update.message.reply_text(
            "✅ Спасибо! Справка будет оформлена в течение 30 дней."
        )
        return ConversationHandler.END

    await update.message.reply_text("Пришлите фото чеков:")
    return RECEIPTS


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
            MORE_PHOTOS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, more_photos),
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
