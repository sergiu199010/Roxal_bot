import os
import requests
import time
import telebot
from datetime import datetime, timedelta
import pytz

# === Настройки ===
CHECK_INTERVAL = 55  # проверка каждые 55 секунд
TIMEZONE = "UTC+1"

# Получаем токен и ID канала из переменных окружения Railway
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# === Валютные пары ===
PAIRS = [
    "EUR/USD", "GBP/AUD", "GBP/CHF", "GBP/USD", "USD/CHF", "USD/JPY",
    "GBP/CAD", "AUD/CAD", "AUD/USD", "USD/CAD", "GBP/JPY", "EUR/JPY",
    "AUD/CHF", "AUD/JPY", "CAD/CHF", "CAD/JPY", "CHF/JPY", "EUR/AUD",
    "EUR/CAD", "EUR/CHF", "EUR/GBP"
]

# === Получение цены с Bitget ===
def get_price(symbol):
    """Пытается получить цену в разных форматах символа (EUR/USD, EURUSD, EURUSDT)."""
    base_url = "https://api.bitget.com/api/v2/market/ticker"
    formats = [
        symbol.replace("/", ""),         # EURUSD
        symbol.replace("/", "") + "T",   # EURUSDT (на всякий случай)
        symbol.replace("/", "") + "USDT" # EURUSD -> EURUSDT
    ]
    for fmt in formats:
        try:
            response = requests.get(base_url, params={"symbol": fmt})
            if response.status_code == 200:
                data = response.json()
                if "data" in data and isinstance(data["data"], dict):
                    return float(data["data"].get("lastPr", 0))
        except Exception as e:
            print(f"Ошибка получения цены для {fmt}: {e}")
    print(f"⚠️ Не удалось получить цену для {symbol}")
    return None

# === Получение максимумов/минимумов (фиктивно для примера) ===
def get_high_low(symbol, hours=24):
    """Эмуляция данных уровней (в реальном коде здесь будет запрос к API)."""
    price = get_price(symbol)
    if price:
        return price * 0.995, price * 1.005  # пример: мин/макс в пределах ±0.5%
    return None, None

# === Проверка и отправка сигналов ===
def check_levels():
    tz = pytz.timezone("Europe/Berlin")  # для UTC+1
    now = datetime.now(tz)
    for pair in PAIRS:
        price = get_price(pair)
        if not price:
            continue

        low_24, high_24 = get_high_low(pair, 24)
        low_12, high_12 = get_high_low(pair, 12)
        low_1, high_1 = get_high_low(pair, 1)

        if not all([low_24, high_24, low_12, high_12, low_1, high_1]):
            continue

        near = None
        if abs(price - high_24) / high_24 < 0.001:
            near = f"MAX (24ч): {high_24:.5f}"
        elif abs(price - low_24) / low_24 < 0.001:
            near = f"MIN (24ч): {low_24:.5f}"
        elif abs(price - high_12) / high_12 < 0.001:
            near = f"MAX (12ч): {high_12:.5f}"
        elif abs(price - low_12) / low_12 < 0.001:
            near = f"MIN (12ч): {low_12:.5f}"
        elif abs(price - high_1) / high_1 < 0.001:
            near = f"MAX (1ч): {high_1:.5f}"
        elif abs(price - low_1) / low_1 < 0.001:
            near = f"MIN (1ч): {low_1:.5f}"

        if near:
            msg = (
                f"⚠️ {pair}\n"
                f"Цена: {price:.5f}\n"
                f"Близко к {near}\n"
                f"🕐 {now.strftime('%H:%M')} ({TIMEZONE})"
            )
            bot.send_message(TELEGRAM_CHAT_ID, msg)
            print(msg)

# === Проверка токена Telegram ===
def test_token():
    try:
        response = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe")
        if response.status_code == 200 and response.json().get("ok"):
            print("✅ Telegram токен действителен. Продолжаю запуск.")
            return True
    except Exception as e:
        print(f"❌ Ошибка проверки токена: {e}")
    return False

# === Основной цикл ===
def main():
    if not test_token():
        print("❌ Остановка: неверный Telegram токен.")
        return

    # Удаляем старый вебхук (чтобы не было конфликта 409)
    try:
        print("🧹 Удаляю старый вебхук...")
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook")
    except:
        pass

    print("🚀 Бот запущен. Ожидает /start в Telegram.")

    @bot.message_handler(commands=["start"])
    def start_message(message):
        bot.reply_to(message, "✅ Бот активен. Проверяю уровни по всем валютным парам каждые 55 секунд.")

        while True:
            check_levels()
            time.sleep(CHECK_INTERVAL)

    bot.infinity_polling(timeout=10, long_polling_timeout=5)

if __name__ == "__main__":
    main()
