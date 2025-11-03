import os
import time
import requests
import telebot
from datetime import datetime, timedelta

# === Настройки ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
EXCHANGE = os.getenv("EXCHANGE", "bitget")

# Проверка токена перед запуском
def check_token_validity(token):
    try:
        test_url = f"https://api.telegram.org/bot{token}/getMe"
        response = requests.get(test_url, timeout=10)
        if response.status_code == 200 and response.json().get("ok"):
            print("✅ Telegram токен действителен. Продолжаю запуск.")
            return True
        else:
            print(f"❌ Ошибка: неверный Telegram токен ({response.status_code}).")
            return False
    except Exception as e:
        print(f"⚠️ Ошибка проверки токена: {e}")
        return False

if not TELEGRAM_TOKEN or not check_token_validity(TELEGRAM_TOKEN):
    print("⛔ Бот не запущен. Проверь токен TELEGRAM_TOKEN в Railway.")
    exit()

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# === Валютные пары ===
PAIRS = [
    "EUR/USD", "GBP/AUD", "GBP/CHF", "GBP/USD", "USD/CHF", "USD/JPY",
    "GBP/CAD", "AUD/CAD", "AUD/USD", "USD/CAD", "GBP/JPY", "EUR/JPY",
    "AUD/CHF", "AUD/JPY", "CAD/CHF", "CAD/JPY", "CHF/JPY",
    "EUR/AUD", "EUR/CAD", "EUR/CHF", "EUR/GBP"
]

# === Получение котировок с Bitget ===
def get_price(symbol):
    try:
        s = symbol.replace("/", "")
        url = f"https://api.bitget.com/api/v2/market/ticker?symbol={s}_SPBL"
        r = requests.get(url, timeout=10).json()
        data = r.get("data", [])
        if not data:
            return None
        return float(data["lastPr"])
    except Exception:
        return None

# === Проверка уровней ===
def check_levels():
    for pair in PAIRS:
        price = get_price(pair)
        if not price:
            continue
        # Здесь твоя логика проверки уровней максимум/минимум
        print(f"{datetime.now().strftime('%H:%M:%S')} Проверена пара {pair}: {price}")

# === Команды Telegram ===
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "✅ Бот активен. Проверяю уровни по всем валютным парам каждые 55 секунд."
    )
    while True:
        check_levels()
        time.sleep(55)

# === Запуск ===
if __name__ == "__main__":
    print("Удаляю вебхук перед запуском опроса...")
    try:
        bot.remove_webhook()
    except Exception:
        pass
    print("Бот запущен. Ожидает /start в Telegram.")
    bot.polling(non_stop=True, skip_pending=True)
