import os
import logging
from datetime import datetime
from flask import Flask, request, abort
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

# Секреты из переменных окружения
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/secretwebhook")

# Проверяем, что всё подтянулось
logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger.info("=== ПРИЛОЖЕНИЕ ЗАПУСКАЕТСЯ НА RENDER ===")
logger.info(f"Время запуска: {datetime.now().isoformat()}")
logger.info(f"TELEGRAM_BOT_TOKEN подтянут: {'да' if TOKEN else 'НЕТ!!!'}")
logger.info(f"ADMIN_CHAT_ID подтянут: {ADMIN_CHAT_ID}")
logger.info(f"WEBHOOK_PATH подтянут: {WEBHOOK_PATH}")

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN НЕ НАЙДЕН В ПЕРЕМЕННЫХ ОКРУЖЕНИЯ!")
if not ADMIN_CHAT_ID:
    raise ValueError("ADMIN_CHAT_ID НЕ НАЙДЕН В ПЕРЕМЕННЫХ ОКРУЖЕНИЯ!")
ADMIN_CHAT_ID = int(ADMIN_CHAT_ID)

app = Flask(__name__)

FIO, BIRTHDATE, INN, METHOD, EMAIL, CHEKS = range(6)

application = Application.builder().token(TOKEN).build()

# Обработчики с логами
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    logger.info(f"=== ПОЛЬЗОВАТЕЛЬ ЗАПУСТИЛ /start ===")
    logger.info(f"User ID: {user.id}, Username: @{user.username}, Имя: {user.full_name}")
    await update.message.reply_text('Привет! Давай оформим справку.\nВведи свое ФИО:')
    return FIO

async def fio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info(f"Получено ФИО: {update.message.text}")
    context.user_data['fio'] = update.message.text.strip()
    await update.message.reply_text('Теперь введи дату рождения (ДД.ММ.ГГГГ):')
    return BIRTHDATE

async def birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info(f"Получена дата рождения: {update.message.text}")
    context.user_data['birthdate'] = update.message.text.strip()
    await update.message.reply_text('Введи ИНН:')
    return INN

async def inn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info(f"Получен ИНН: {update.message.text}")
    context.user_data['inn'] = update.message.text.strip()
    reply_keyboard = [['Оригинал на бумаге', 'На email']]
    await update.message.reply_text(
        'Выбери способ получения справки:',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return METHOD

async def method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info(f"Выбран способ: {update.message.text}")
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
    logger.info(f"Получен email: {update.message.text}")
    context.user_data['email'] = update.message.text.strip()
    await update.message.reply_text('Теперь пришли фото чеков об оплате\nили напиши "Чеков нет":')
    return CHEKS

async def cheks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("=== ЗАШЛИ В ФУНКЦИЮ ОБРАБОТКИ ЧЕКОВ ===")
    photo_path = None

    if update.message.photo:
        logger.info("Получено фото чека")
        # Закомментировано, чтобы не падать на файловой системе Render free
        # photo = update.message.photo[-1]
        # file = await photo.get_file()
        # photo_path = f"chek_{update.effective_user.id}_{photo.file_id[-8:]}.jpg"
        # await file.download_to_drive(photo_path)
        context.user_data['cheks'] = 'Фото чеков получено (но не сохранено)'
    elif update.message.text and update.message.text.lower() in ['чеков нет', 'нет чеков', 'нет']:
        logger.info("Пользователь выбрал 'Чеков нет'")
        context.user_data['cheks'] = 'Чеков нет'
    else:
        logger.warning(f"Неизвестный ввод в чеках: {update.message.text}")
        await update.message.reply_text('Пожалуйста, пришли фото или напиши "Чеков нет".')
        return CHEKS

    summary = (
        f"🆕 НОВАЯ ЗАЯВКА!\n\n"
        f"ФИО: {context.user_data.get('fio', '—')}\n"
        f"Дата рождения: {context.user_data.get('birthdate', '—')}\n"
        f"ИНН: {context.user_data.get('inn', '—')}\n"
        f"Способ: {context.user_data.get('method', '—')}\n"
        f"Email: {context.user_data.get('email', 'Не указан')}\n"
        f"Чеки: {context.user_data.get('cheks', '—')}\n\n"
        f"От: {update.effective_user.full_name} (@{update.effective_user.username or 'нет'})\n"
        f"ID: {update.effective_user.id}\n"
        f"Время: {update.message.date}"
    )

    logger.info("Отправляем сводку админу...")
    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=summary)
        logger.info("Сводка успешно отправлена админу")
    except Exception as e:
        logger.error(f"Ошибка отправки админу: {str(e)}")

    await update.message.reply_text('Спасибо! Справка будет оформлена в течение 30 дней.')
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("Пользователь отменил процесс (/cancel)")
    await update.message.reply_text('Отменено.', reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

# Настройка ConversationHandler
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

# Самый важный блок — webhook с максимальными логами
@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    logger.info("=== НОВЫЙ WEBHOOK ЗАПРОС ОТ TELEGRAM ===")
    logger.info(f"Время: {datetime.now().isoformat()}")
    logger.info(f"Путь запроса: {request.path}")
    logger.info(f"Метод: {request.method}")
    logger.info(f"Headers: {dict(request.headers)}")

    if request.headers.get('content-type') != 'application/json':
        logger.warning("Неверный Content-Type от Telegram!")
        return 'Bad Content-Type', 400

    logger.info("Чтение JSON от Telegram...")
    try:
        json_data = request.get_json(force=True, silent=False)
        logger.info("JSON успешно прочитан")
        logger.info(f"Длина JSON: {len(str(json_data))}")
        logger.info(f"Ключи в JSON: {list(json_data.keys())}")
    except Exception as e:
        logger.error(f"Ошибка парсинга JSON: {str(e)}")
        logger.error(f"Сырые данные: {request.data[:500]}...")
        return 'Invalid JSON', 400

    if not json_data:
        logger.error("JSON пустой")
        return 'Empty JSON', 400

    logger.info("Создание объекта Update...")
    try:
        update = Update.de_json(json_data, application.bot)
        logger.info(f"Update создан. Тип: {type(update)}, Update ID: {getattr(update, 'update_id', 'нет')}")
    except Exception as e:
        logger.error(f"Ошибка создания Update: {str(e)}")
        return 'Update error', 400

    logger.info("Запуск process_update...")
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.process_update(update))
        logger.info("process_update выполнен успешно")
    except Exception as e:
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА В PROCESS_UPDATE: {str(e)}", exc_info=True)
        return 'Processing failed', 500

    logger.info("Всё ОК, возвращаем 200")
    return 'OK', 200

@app.route('/')
def index():
    logger.info("Кто-то зашёл на главную страницу")
    return 'Бот работает! Напиши ему в Telegram.'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Запуск Flask на порту {port}")
    app.run(host='0.0.0.0', port=port)
