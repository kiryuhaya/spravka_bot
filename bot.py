import os
import logging
from flask import Flask, request, abort
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
    Dispatcher
)

# Настройки (секреты берём из переменных окружения)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")  # по умолчанию /webhook, но позже изменим

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан в переменных окружения!")
if not ADMIN_CHAT_ID:
    raise ValueError("ADMIN_CHAT_ID не задан в переменных окружения!")

app = Flask(__name__)

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния
FIO, BIRTHDATE, INN, METHOD, EMAIL, CHEKS = range(6)

application = Application.builder().token(TOKEN).build()

# Функции обработчики (все как раньше, без изменений)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Привет! Давай оформим справку.\nВведи свое ФИО:')
    return FIO

async def fio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['fio'] = update.message.text.strip()
    await update.message.reply_text('Теперь введи дату рождения (ДД.ММ.ГГГГ):')
    return BIRTHDATE

async def birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['birthdate'] = update.message.text.strip()
    await update.message.reply_text('Введи ИНН:')
    return INN

async def inn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['inn'] = update.message.text.strip()
    reply_keyboard = [['Оригинал на бумаге', 'На email']]
    await update.message.reply_text(
        'Выбери способ получения справки:',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return METHOD

async def method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['method'] = update.message.text
    if context.user_data['method'] == 'На email':
        await update.message.reply_text('Введи email:', reply_markup=ReplyKeyboardRemove())
        return EMAIL
    else:
        await update.message.reply_text(
            'Теперь пришли фото чеков об оплате\nили напиши "Чеков нет":',
            reply_markup=ReplyKeyboardRemove()
        )
        return CHEKS

async def email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['email'] = update.message.text.strip()
    await update.message.reply_text('Теперь пришли фото чеков об оплате\nили напиши "Чеков нет":')
    return CHEKS

async def cheks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    photo_path = None
    if update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        photo_path = f"chek_{update.effective_user.id}_{photo.file_id[-8:]}.jpg"
        await file.download_to_drive(photo_path)
        context.user_data['cheks'] = 'Фото чеков получено'
    elif update.message.text and update.message.text.lower() in ['чеков нет', 'нет чеков', 'нет']:
        context.user_data['cheks'] = 'Чеков нет'
    else:
        await update.message.reply_text('Пожалуйста, пришли фото или напиши "Чеков нет".')
        return CHEKS

    summary = (
        "🆕 НОВАЯ ЗАЯВКА!\n\n"
        f"ФИО: {context.user_data.get('fio', '—')}\n"
        f"Дата рождения: {context.user_data.get('birthdate', '—')}\n"
        f"ИНН: {context.user_data.get('inn', '—')}\n"
        f"Способ: {context.user_data.get('method', '—')}\n"
        f"Email: {context.user_data.get('email', 'Не указан')}\n"
        f"Чеки: {context.user_data.get('cheks', '—')}\n"
        f"\nОт: {update.effective_user.full_name} (@{update.effective_user.username or 'нет'})\n"
        f"ID: {update.effective_user.id}\n"
        f"Время: {update.message.date}"
    )

    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=summary)
        if photo_path:
            await context.bot.send_photo(chat_id=ADMIN_CHAT_ID, photo=open(photo_path, 'rb'))
            os.remove(photo_path)
    except Exception as e:
        logger.error(f"Ошибка отправки админу: {e}")

    await update.message.reply_text('Спасибо! Справка будет оформлена в течение 30 дней.')
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Отменено.', reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

# Настройка обработчиков
def setup_handlers():
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, fio)],
            BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, birthdate)],
            INN: [MessageHandler(filters.TEXT & ~filters.COMMAND, inn)],
            METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, method)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email)],
            CHEKS: [MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), cheks)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True,
    )
    application.add_handler(conv_handler)

setup_handlers()

# Webhook (синхронный, работает на Render)
dispatcher = application.dispatcher

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_data = request.get_json()
        if json_data:
            update = Update.de_json(json_data, application.bot)
            if update:
                dispatcher.process_update(update)
        return 'OK', 200
    abort(403)

@app.route('/')
def index():
    return 'Бот работает!'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
