import os
import logging
from datetime import datetime
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
import asyncio
from threading import Thread

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получение переменных окружения
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
WEBHOOK_PATH = os.getenv('WEBHOOK_PATH')
RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL')

logger.info(f"Переменные окружения загружены:")
logger.info(f"TOKEN: {'установлен' if TOKEN else 'НЕ УСТАНОВЛЕН'}")
logger.info(f"ADMIN_CHAT_ID: {ADMIN_CHAT_ID}")
logger.info(f"WEBHOOK_PATH: {WEBHOOK_PATH}")
logger.info(f"RENDER_EXTERNAL_URL: {RENDER_EXTERNAL_URL}")

# Проверка обязательных переменных
if not TOKEN or not ADMIN_CHAT_ID or not WEBHOOK_PATH:
    logger.error("КРИТИЧЕСКАЯ ОШИБКА: Не установлены обязательные переменные окружения!")
    raise ValueError("Отсутствуют обязательные переменные окружения")

# Состояния диалога
(
    FULLNAME,
    BIRTHDATE,
    INN,
    DELIVERY_METHOD,
    EMAIL,
    RECEIPTS,
) = range(6)

# Хранилище данных пользователей (в продакшене использовать БД)
user_data_storage = {}

# Flask приложение
app = Flask(__name__)

# Telegram Application
application = Application.builder().token(TOKEN).build()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало диалога"""
    logger.info(f"Пользователь {update.effective_user.id} ({update.effective_user.username}) начал диалог")
    
    user_id = update.effective_user.id
    user_data_storage[user_id] = {
        'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'username': update.effective_user.username or 'Не указан'
    }
    
    await update.message.reply_text(
        "Добро пожаловать! Я помогу вам оформить справку.\n\n"
        "Пожалуйста, введите ваше ФИО (полностью):"
    )
    return FULLNAME


async def fullname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ФИО"""
    user_id = update.effective_user.id
    fullname_text = update.message.text.strip()
    
    logger.info(f"Пользователь {user_id} ввел ФИО: {fullname_text}")
    
    user_data_storage[user_id]['fullname'] = fullname_text
    
    await update.message.reply_text(
        "Отлично! Теперь введите дату рождения в формате ДД.ММ.ГГГГ\n"
        "Например: 15.03.1990"
    )
    return BIRTHDATE


async def birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка даты рождения"""
    user_id = update.effective_user.id
    birthdate_text = update.message.text.strip()
    
    logger.info(f"Пользователь {user_id} ввел дату рождения: {birthdate_text}")
    
    # Простая валидация формата
    if len(birthdate_text) != 10 or birthdate_text.count('.') != 2:
        logger.warning(f"Неверный формат даты от пользователя {user_id}")
        await update.message.reply_text(
            "Неверный формат даты. Пожалуйста, используйте формат ДД.ММ.ГГГГ\n"
            "Например: 15.03.1990"
        )
        return BIRTHDATE
    
    user_data_storage[user_id]['birthdate'] = birthdate_text
    
    await update.message.reply_text(
        "Хорошо! Теперь введите ваш ИНН (12 цифр):"
    )
    return INN


async def inn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ИНН"""
    user_id = update.effective_user.id
    inn_text = update.message.text.strip()
    
    logger.info(f"Пользователь {user_id} ввел ИНН: {inn_text}")
    
    # Валидация ИНН (должен быть 10 или 12 цифр)
    if not inn_text.isdigit() or len(inn_text) not in [10, 12]:
        logger.warning(f"Неверный формат ИНН от пользователя {user_id}")
        await update.message.reply_text(
            "ИНН должен содержать 10 или 12 цифр. Попробуйте еще раз:"
        )
        return INN
    
    user_data_storage[user_id]['inn'] = inn_text
    
    # Кнопки для выбора способа получения
    keyboard = [
        ["Оригинал на бумаге"],
        ["На email"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Отлично! Выберите способ получения справки:",
        reply_markup=reply_markup
    )
    return DELIVERY_METHOD


async def delivery_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка способа получения"""
    user_id = update.effective_user.id
    method = update.message.text.strip()
    
    logger.info(f"Пользователь {user_id} выбрал способ: {method}")
    
    if method not in ["Оригинал на бумаге", "На email"]:
        await update.message.reply_text(
            "Пожалуйста, выберите один из предложенных вариантов:",
            reply_markup=ReplyKeyboardMarkup(
                [["Оригинал на бумаге"], ["На email"]],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return DELIVERY_METHOD
    
    user_data_storage[user_id]['delivery_method'] = method
    
    if method == "На email":
        await update.message.reply_text(
            "Пожалуйста, введите ваш email адрес:",
            reply_markup=ReplyKeyboardRemove()
        )
        return EMAIL
    else:
        # Переходим сразу к чекам
        keyboard = [["Чеков нет"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            "Теперь отправьте фото чеков об оплате или нажмите кнопку \"Чеков нет\":",
            reply_markup=reply_markup
        )
        user_data_storage[user_id]['email'] = 'Не требуется'
        user_data_storage[user_id]['receipts'] = []
        return RECEIPTS


async def email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка email"""
    user_id = update.effective_user.id
    email_text = update.message.text.strip()
    
    logger.info(f"Пользователь {user_id} ввел email: {email_text}")
    
    # Простая валидация email
    if '@' not in email_text or '.' not in email_text:
        logger.warning(f"Неверный формат email от пользователя {user_id}")
        await update.message.reply_text(
            "Неверный формат email. Пожалуйста, введите корректный адрес:"
        )
        return EMAIL
    
    user_data_storage[user_id]['email'] = email_text
    user_data_storage[user_id]['receipts'] = []
    
    keyboard = [["Чеков нет"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Отлично! Теперь отправьте фото чеков об оплате или нажмите кнопку \"Чеков нет\":",
        reply_markup=reply_markup
    )
    return RECEIPTS


async def receipts_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото чеков"""
    user_id = update.effective_user.id
    
    if update.message.photo:
        logger.info(f"Пользователь {user_id} отправил фото чека")
        
        # Получаем фото в лучшем качестве
        photo = update.message.photo[-1]
        user_data_storage[user_id]['receipts'].append(photo.file_id)
        
        # Пересылаем фото админу немедленно
        try:
            await context.bot.send_photo(
                chat_id=ADMIN_CHAT_ID,
                photo=photo.file_id,
                caption=f"📸 Чек от пользователя {user_id} (@{user_data_storage[user_id]['username']})"
            )
            logger.info(f"Фото чека от пользователя {user_id} отправлено админу")
        except Exception as e:
            logger.error(f"Ошибка при отправке фото админу: {e}")
        
        await update.message.reply_text(
            "Фото получено! Можете отправить еще чеки или нажмите \"Чеков нет\" для завершения.",
            reply_markup=ReplyKeyboardMarkup(
                [["Чеков нет"]],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return RECEIPTS


async def receipts_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текста в состоянии RECEIPTS"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if text == "Чеков нет":
        logger.info(f"Пользователь {user_id} завершил отправку чеков")
        return await finish_registration(update, context)
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото чеков или нажмите \"Чеков нет\":",
            reply_markup=ReplyKeyboardMarkup(
                [["Чеков нет"]],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return RECEIPTS


async def finish_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение регистрации и отправка данных админу"""
    user_id = update.effective_user.id
    data = user_data_storage.get(user_id, {})
    
    logger.info(f"Завершение регистрации пользователя {user_id}")
    
    # Формируем сообщение для админа
    admin_message = f"""
<b>НОВАЯ ЗАЯВКА НА СПРАВКУ</b>

<b>Информация о пользователе:</b>
• ID: <code>{user_id}</code>
• Username: @{data.get('username', 'Не указан')}
• Время заявки: {data.get('start_time', 'Не указано')}

<b>Данные заявки:</b>
• ФИО: {data.get('fullname', 'Не указано')}
• Дата рождения: {data.get('birthdate', 'Не указано')}
• ИНН: {data.get('inn', 'Не указано')}
• Способ получения: {data.get('delivery_method', 'Не указано')}
• Email: {data.get('email', 'Не указано')}
• Количество чеков: {len(data.get('receipts', []))}
"""
    
    # Отправляем данные админу
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_message,
            parse_mode='HTML'
        )
        logger.info(f"Данные пользователя {user_id} отправлены админу")
    except Exception as e:
        logger.error(f"Ошибка при отправке данных админу: {e}")
    
    # Отправляем подтверждение пользователю
    await update.message.reply_text(
        "Спасибо! Справка будет оформлена в течение 30 дней.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Очищаем данные пользователя
    if user_id in user_data_storage:
        del user_data_storage[user_id]
    
    logger.info(f"Регистрация пользователя {user_id} успешно завершена")
    
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена диалога"""
    user_id = update.effective_user.id
    logger.info(f"Пользователь {user_id} отменил диалог")
    
    if user_id in user_data_storage:
        del user_data_storage[user_id]
    
    await update.message.reply_text(
        "Операция отменена. Для начала введите /start",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# Обработчик диалога
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fullname)],
        BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, birthdate)],
        INN: [MessageHandler(filters.TEXT & ~filters.COMMAND, inn)],
        DELIVERY_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, delivery_method)],
        EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email)],
        RECEIPTS: [
            MessageHandler(filters.PHOTO, receipts_photo),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receipts_text),
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

application.add_handler(conv_handler)


@app.route('/')
def index():
    """Главная страница"""
    logger.info("Главная страница запрошена")
    return "Telegram Bot is running!"


@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    """Обработчик webhook"""
    try:
        logger.info("Получен webhook запрос")
        json_data = request.get_json(force=True)
        logger.info(f"Webhook данные: {json_data}")
        
        update = Update.de_json(json_data, application.bot)
        
        # Создаем новый event loop для обработки
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(application.process_update(update))
            logger.info("Update обработан успешно")
        finally:
            loop.close()
        
        return 'OK', 200
    except Exception as e:
        logger.error(f"ОШИБКА в webhook: {e}", exc_info=True)
        return 'ERROR', 500


async def setup_webhook():
    """Установка webhook"""
    webhook_url = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"
    logger.info(f"Устанавливаем webhook: {webhook_url}")
    
    try:
        await application.bot.set_webhook(url=webhook_url)
        webhook_info = await application.bot.get_webhook_info()
        logger.info(f"Webhook установлен: {webhook_info.url}")
        logger.info(f"Pending updates: {webhook_info.pending_update_count}")
    except Exception as e:
        logger.error(f"Ошибка при установке webhook: {e}")


def run_setup():
    """Запуск setup в отдельном потоке"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(setup_webhook())
    loop.close()


if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("ЗАПУСК БОТА")
    logger.info("=" * 50)
    
    # Устанавливаем webhook в отдельном потоке
    setup_thread = Thread(target=run_setup)
    setup_thread.start()
    setup_thread.join()
    
    # Запускаем Flask
    port = int(os.getenv('PORT', 10000))
    logger.info(f"Запуск Flask на порту {port}")
    app.run(host='0.0.0.0', port=port)
