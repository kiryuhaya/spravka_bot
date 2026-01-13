import os
import logging
import asyncio
from datetime import datetime
from threading import Thread
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

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем переменные окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
PORT = int(os.getenv('PORT', 8443))

# Проверка обязательных переменных
if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN не установлен")
    raise ValueError("TELEGRAM_TOKEN обязателен")
if not ADMIN_CHAT_ID:
    logger.error("ADMIN_CHAT_ID не установлен")
    raise ValueError("ADMIN_CHAT_ID обязателен")
if not WEBHOOK_URL:
    logger.error("WEBHOOK_URL не установлен")
    raise ValueError("WEBHOOK_URL обязателен")

logger.info(f"Бот запускается с WEBHOOK_URL: {WEBHOOK_URL}")
logger.info(f"ADMIN_CHAT_ID: {ADMIN_CHAT_ID}")

# Состояния диалога
(FIO, BIRTHDATE, INN, DELIVERY_METHOD, EMAIL, RECEIPTS) = range(6)

# Flask приложение
app = Flask(__name__)

# Telegram Application
application = Application.builder().token(TELEGRAM_TOKEN).build()

# Хранилище данных пользователей
user_data_storage = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога - запрос ФИО"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} ({user.username}) начал диалог")
    
    # Инициализируем хранилище для пользователя
    user_data_storage[user.id] = {
        'user_id': user.id,
        'username': user.username,
        'start_time': datetime.now().isoformat()
    }
    
    await update.message.reply_text(
        "Добро пожаловать! Я помогу вам оформить справку.\n\n"
        "Пожалуйста, укажите ваше ФИО (Фамилия Имя Отчество):",
        reply_markup=ReplyKeyboardRemove()
    )
    return FIO


async def get_fio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение ФИО и запрос даты рождения"""
    user_id = update.effective_user.id
    fio = update.message.text.strip()
    
    logger.info(f"Пользователь {user_id} ввёл ФИО: {fio}")
    
    user_data_storage[user_id]['fio'] = fio
    
    await update.message.reply_text(
        "Спасибо!\n\n"
        "Теперь укажите вашу дату рождения в формате ДД.ММ.ГГГГ\n"
        "Например: 15.03.1990"
    )
    return BIRTHDATE


async def get_birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение даты рождения и запрос ИНН"""
    user_id = update.effective_user.id
    birthdate = update.message.text.strip()
    
    logger.info(f"Пользователь {user_id} ввёл дату рождения: {birthdate}")
    
    # Простая валидация формата
    try:
        datetime.strptime(birthdate, '%d.%m.%Y')
        user_data_storage[user_id]['birthdate'] = birthdate
    except ValueError:
        logger.warning(f"Пользователь {user_id} ввёл неверный формат даты: {birthdate}")
        await update.message.reply_text(
            "Неверный формат даты. Пожалуйста, используйте формат ДД.ММ.ГГГГ\n"
            "Например: 15.03.1990"
        )
        return BIRTHDATE
    
    await update.message.reply_text(
        "Отлично!\n\n"
        "Теперь укажите ваш ИНН (12 цифр):"
    )
    return INN


async def get_inn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение ИНН и запрос способа получения"""
    user_id = update.effective_user.id
    inn = update.message.text.strip()
    
    logger.info(f"Пользователь {user_id} ввёл ИНН: {inn}")
    
    # Валидация ИНН (12 цифр)
    if not inn.isdigit() or len(inn) != 12:
        logger.warning(f"Пользователь {user_id} ввёл неверный ИНН: {inn}")
        await update.message.reply_text(
            "ИНН должен состоять из 12 цифр. Пожалуйста, попробуйте снова:"
        )
        return INN
    
    user_data_storage[user_id]['inn'] = inn
    
    # Клавиатура с выбором способа получения
    keyboard = [
        ["Оригинал на бумаге"],
        ["На email"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Прекрасно!\n\n"
        "Выберите способ получения справки:",
        reply_markup=reply_markup
    )
    return DELIVERY_METHOD


async def get_delivery_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение способа доставки"""
    user_id = update.effective_user.id
    method = update.message.text.strip()
    
    logger.info(f"Пользователь {user_id} выбрал способ получения: {method}")
    
    user_data_storage[user_id]['delivery_method'] = method
    
    if method == "На email":
        await update.message.reply_text(
            "Укажите ваш email адрес:",
            reply_markup=ReplyKeyboardRemove()
        )
        return EMAIL
    else:
        # Переходим к запросу чеков
        return await ask_for_receipts(update, context)


async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение email"""
    user_id = update.effective_user.id
    email = update.message.text.strip()
    
    logger.info(f"Пользователь {user_id} указал email: {email}")
    
    # Простая валидация email
    if '@' not in email or '.' not in email:
        logger.warning(f"Пользователь {user_id} ввёл неверный email: {email}")
        await update.message.reply_text(
            "Неверный формат email. Пожалуйста, укажите корректный email адрес:"
        )
        return EMAIL
    
    user_data_storage[user_id]['email'] = email
    
    return await ask_for_receipts(update, context)


async def ask_for_receipts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос чеков об оплате"""
    user_id = update.effective_user.id
    logger.info(f"Запрашиваем чеки у пользователя {user_id}")
    
    # Инициализируем список чеков
    user_data_storage[user_id]['receipts'] = []
    
    keyboard = [["Чеков нет"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Теперь отправьте фото чеков об оплате.\n"
        "Вы можете отправить несколько фотографий одну за другой.\n"
        "Когда закончите, нажмите кнопку 'Чеков нет' или отправьте текст 'готово'.",
        reply_markup=reply_markup
    )
    return RECEIPTS


async def get_receipts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение чеков (фото или текст 'готово'/'Чеков нет')"""
    user_id = update.effective_user.id
    
    # Если пользователь написал "Чеков нет" или "готово"
    if update.message.text:
        text = update.message.text.strip().lower()
        logger.info(f"Пользователь {user_id} отправил текст: {text}")
        
        if text in ['чеков нет', 'готово']:
            if text == 'чеков нет':
                user_data_storage[user_id]['receipts_status'] = 'Чеков нет'
            else:
                user_data_storage[user_id]['receipts_status'] = f"Отправлено фото: {len(user_data_storage[user_id]['receipts'])}"
            
            return await finalize_application(update, context)
        else:
            await update.message.reply_text(
                "Пожалуйста, отправьте фото чека или нажмите 'Чеков нет'."
            )
            return RECEIPTS
    
    # Если пользователь отправил фото
    if update.message.photo:
        photo = update.message.photo[-1]  # Берём фото лучшего качества
        logger.info(f"Пользователь {user_id} отправил фото чека: {photo.file_id}")
        
        try:
            # Отправляем фото администратору сразу
            await context.bot.send_photo(
                chat_id=ADMIN_CHAT_ID,
                photo=photo.file_id,
                caption=f"Чек от пользователя {user_id} (@{user_data_storage[user_id].get('username', 'нет username')})"
            )
            logger.info(f"Фото чека от пользователя {user_id} отправлено администратору")
            
            # Сохраняем file_id в данных пользователя
            user_data_storage[user_id]['receipts'].append(photo.file_id)
            
            await update.message.reply_text(
                "Чек получен! Можете отправить ещё фото или нажать 'Чеков нет' для завершения."
            )
            return RECEIPTS
            
        except Exception as e:
            logger.error(f"Ошибка при отправке фото администратору: {e}")
            await update.message.reply_text(
                "Произошла ошибка при обработке фото. Попробуйте снова."
            )
            return RECEIPTS
    
    await update.message.reply_text(
        "Пожалуйста, отправьте фото чека или нажмите 'Чеков нет'."
    )
    return RECEIPTS


async def finalize_application(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Завершение заявки и отправка данных администратору"""
    user_id = update.effective_user.id
    logger.info(f"Финализация заявки пользователя {user_id}")
    
    data = user_data_storage.get(user_id, {})
    
    # Формируем сообщение для администратора
    admin_message = (
        "НОВАЯ ЗАЯВКА НА СПРАВКУ\n\n"
        f"ФИО: {data.get('fio', 'не указано')}\n"
        f"Дата рождения: {data.get('birthdate', 'не указано')}\n"
        f"ИНН: {data.get('inn', 'не указано')}\n"
        f"Способ получения: {data.get('delivery_method', 'не указано')}\n"
    )
    
    if 'email' in data:
        admin_message += f"📧 Email: {data['email']}\n"
    
    admin_message += (
        f"Чеки: {data.get('receipts_status', 'Отправлено фото: ' + str(len(data.get('receipts', []))))}\n\n"
        f"User ID: {data.get('user_id', 'неизвестно')}\n"
        f"Username: @{data.get('username', 'нет username')}\n"
        f"Время подачи: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
    )
    
    try:
        # Отправляем сводку администратору
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_message
        )
        logger.info(f"Данные заявки от пользователя {user_id} отправлены администратору")
        
        # Благодарим пользователя
        await update.message.reply_text(
            "Спасибо! Справка будет оформлена в течение 30 дней.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Очищаем данные пользователя
        if user_id in user_data_storage:
            del user_data_storage[user_id]
        
        logger.info(f"Заявка пользователя {user_id} успешно обработана")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке данных администратору: {e}")
        await update.message.reply_text(
            "Произошла ошибка при отправке заявки. Пожалуйста, попробуйте позже или свяжитесь с администратором."
        )
    
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена диалога"""
    user_id = update.effective_user.id
    logger.info(f"Пользователь {user_id} отменил диалог")
    
    if user_id in user_data_storage:
        del user_data_storage[user_id]
    
    await update.message.reply_text(
        "Оформление справки отменено. Если хотите начать заново, отправьте /start",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# Настройка ConversationHandler
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fio)],
        BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_birthdate)],
        INN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_inn)],
        DELIVERY_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_delivery_method)],
        EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
        RECEIPTS: [MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, get_receipts)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

application.add_handler(conv_handler)


# Функция для запуска async кода из sync контекста
def run_async(coro):
    """Запускает корутину в отдельном потоке"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.route('/')
def index():
    """Главная страница для проверки работы сервера"""
    logger.info("Запрос к корневому URL")
    return "Telegram Bot is running!"


@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработчик webhook от Telegram"""
    try:
        logger.info("Получен webhook запрос")
        
        # Получаем данные обновления
        json_data = request.get_json(force=True)
        logger.info(f"Webhook данные: {json_data}")
        
        # Создаём Update объект
        update = Update.de_json(json_data, application.bot)
        
        # Запускаем обработку в отдельном потоке
        thread = Thread(target=run_async, args=(application.process_update(update),))
        thread.start()
        
        logger.info("Webhook обработан успешно")
        return 'OK', 200
        
    except Exception as e:
        logger.error(f"Ошибка при обработке webhook: {e}", exc_info=True)
        return 'Error', 500


@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Установка webhook (для отладки)"""
    try:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        logger.info(f"Попытка установить webhook: {webhook_url}")
        
        result = run_async(application.bot.set_webhook(webhook_url))
        logger.info(f"Webhook установлен: {result}")
        
        return f"Webhook установлен: {webhook_url}", 200
    except Exception as e:
        logger.error(f"Ошибка при установке webhook: {e}", exc_info=True)
        return f"Ошибка: {str(e)}", 500


if __name__ == '__main__':
    logger.info("Запуск Flask приложения")
    logger.info(f"PORT: {PORT}")
    
    # Запускаем Flask приложение
    app.run(host='0.0.0.0', port=PORT)
