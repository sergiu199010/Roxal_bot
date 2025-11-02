import os
import time
import ccxt
import logging
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# Настройки логов
logging.basicConfig(level=logging.INFO)

# Получаем переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
EXCHANGE_NAME = os.getenv("EXCHANGE", "binance").lower()
SYMBOL = os.getenv("SYMBOL", "BTC/USDT")
THRESHOLD = float(os.getenv("THRESHOLD", "0.001"))
POLL_SEC = int(os.getenv("POLL_SEC", "30"))
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", "900"))

# Создаём подключение к бирже
exchange = getattr(ccxt, EXCHANGE_NAME)()

# Создаём телеграм-бота
bot = Bot(token=TELEGRAM_TOKEN)
updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher

# Функция для проверки связи
def ping(update: Update, context: CallbackContext):
    update.message.reply_text("✅ Бот активен и работает!")

dp.add_handler(CommandHandler("ping", ping))

# Основной процесс
def check_price():
    try:
        ticker = exchange.fetch_ticker(SYMBOL)
        last_price = ticker["last"]
        logging.info(f"Текущая цена {SYMBOL}: {last_price}")
        return last_price
    except Exception as e:
        logging.error(f"Ошибка при получении данных: {e}")
        return None

def main_loop():
    last_alert_time = 0
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🤖 Бот запущен и ждёт сигналов...")

    while True:
        price = check_price()
        if price:
            current_time = time.time()
            if current_time - last_alert_time > COOLDOWN_SEC:
                message = f"📊 {SYMBOL} сейчас {price}"
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                last_alert_time = current_time
        time.sleep(POLL_SEC)

if __name__ == "__main__":
    updater.start_polling()
    main_loop()
