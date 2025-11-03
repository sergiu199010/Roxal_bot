import os
import time
import requests
import telebot
from datetime import datetime, timedelta

# === Настройки ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CHECK_INTERVAL = 60  # каждые 60 сек
UTC_OFFSET = 1       # UTC+1

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

# === Валютные пары ===
PAIRS = [
    "EUR/USD", "GBP/AUD", "GBP/CHF", "GBP/USD", "USD/CHF", "USD/JPY",
    "GBP/CAD", "AUD/CAD", "AUD/USD", "USD/CAD", "GBP/JPY", "EUR/JPY",
    "AUD/CHF", "AUD/JPY", "CAD/CHF", "CAD/JPY", "CHF/JPY",
    "EUR/AUD", "EUR/CAD", "EUR/CHF", "EUR/GBP"
]

# === Безопасное получение JSON ===
def safe_json(response):
    try:
        return response.json()
    except:
        return None

# === Получение цены ===
def get_price(symbol):
    s = symbol.replace("/", "")
    try:
        # Bitget
        r1 = requests.get(f"https://api.bitget.com/api/v2/market/ticker?symbol={s}_SPBL", timeout=10)
        j1 = safe_json(r1)
        if j1 and isinstance(j1.get("data"), dict) and "lastPr" in j1["data"]:
            return float(j1["data"]["lastPr"])

        # Binance
        r2 = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={s}", timeout=10)
        j2 = safe_json(r2)
        if j2 and "price" in j2:
            return float(j2["price"])

        # Coinbase резерв
        r3 = requests.get(f"https://api.exchange.coinbase.com/products/{symbol.replace('/', '-')}/ticker", timeout=10)
        j3 = safe_json(r3)
        if j3 and "price" in j3:
            return float(j3["price"])

        print(f"⚠️ Не удалось получить цену для {symbol}")
        return None
    except Exception as e:
        print(f"⚠️ Ошибка получения цены для {symbol}: {e}")
        time.sleep(1)
        return None

# === Получение максимумов и минимумов ===
def get_candles(symbol, interval, limit=100):
    s = symbol.replace("/", "")
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={s}&interval={interval}&limit={limit}"
        r = requests.get(url, timeout=10)
        data = safe_json(r)
        if not data or not isinstance(data, list):
            return None, None
        highs = [float(c[2]) for c in data]
        lows = [float(c[3]) for c in data]
        return max(highs), min(lows)
    except Exception as e:
        print(f"⚠️ Ошибка свечей для {symbol}: {e}")
        time.sleep(1)
        return None, None

# === Проверка уровней ===
def check_levels():
    for pair in PAIRS:
        price = get_price(pair)
        if not price:
            continue

        max_1h, min_1h = get_candles(pair, "1h")
        max_12h, min_12h = get_candles(pair, "4h")
        max_24h, min_24h = get_candles(pair, "1d")

        if not all([max_1h, min_1h, max_12h, min_12h, max_24h, min_24h]):
            continue

        utc_now = datetime.utcnow() + timedelta(hours=UTC_OFFSET)
        time_now = utc_now.strftime("%H:%M (UTC+1)")

        for tf, high, low in [
            ("1h", max_1h, min_1h),
            ("12h", max_12h, min_12h),
            ("24h", max_24h, min_24h)
        ]:
            dist_high = (high - price) / price * 100
            dist_low = (price - low) / price * 100

            if 0 < dist_high <= 0.1:
                bot.send_message(
                    TELEGRAM_CHAT_ID,
                    f"📈 {pair} близко к максимуму {tf}\n"
                    f"Цена: {price}\nMAX: {high}\nДистанция: {dist_high:.3f}%\n🕐 {time_now}"
                )
            elif 0 < dist_low <= 0.1:
                bot.send_message(
                    TELEGRAM_CHAT_ID,
                    f"📉 {pair} близко к минимуму {tf}\n"
                    f"Цена: {price}\nMIN: {low}\nДистанция: {dist_low:.3f}%\n🕐 {time_now}"
                )

        print(f"✅ Проверена пара {pair}: {price}")
        time.sleep(2)  # пауза между парами

# === Команда /start ===
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(message.chat.id, "✅ Бот запущен. Проверяю уровни каждые 60 секунд.")
    while True:
        check_levels()
        time.sleep(CHECK_INTERVAL)

# === Запуск ===
if __name__ == "__main__":
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook")
    except:
        pass
    print("🚀 Бот запущен. Ожидает /start в Telegram.")
    bot.polling(non_stop=True, skip_pending=True)
