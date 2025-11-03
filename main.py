import os
import time
import requests
import telebot
from datetime import datetime, timedelta

# === Настройки ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CHECK_INTERVAL = 55  # секунд
UTC_OFFSET = 1  # часовой пояс UTC+1

# === Проверка токена ===
def check_token_validity(token):
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and r.json().get("ok"):
            print("✅ Telegram токен действителен. Продолжаю запуск.")
            return True
        else:
            print(f"❌ Ошибка токена ({r.status_code}). Проверь TELEGRAM_TOKEN.")
            return False
    except Exception as e:
        print(f"⚠️ Ошибка проверки токена: {e}")
        return False

if not TELEGRAM_TOKEN or not check_token_validity(TELEGRAM_TOKEN):
    print("⛔ Бот не запущен. Проверь TELEGRAM_TOKEN.")
    exit()

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# === Валютные пары ===
PAIRS = [
    "EUR/USD", "GBP/AUD", "GBP/CHF", "GBP/USD", "USD/CHF", "USD/JPY",
    "GBP/CAD", "AUD/CAD", "AUD/USD", "USD/CAD", "GBP/JPY", "EUR/JPY",
    "AUD/CHF", "AUD/JPY", "CAD/CHF", "CAD/JPY", "CHF/JPY",
    "EUR/AUD", "EUR/CAD", "EUR/CHF", "EUR/GBP"
]

# === Получение цены (Bitget → Binance резерв) ===
def get_price(symbol):
    try:
        s = symbol.replace("/", "")
        url1 = f"https://api.bitget.com/api/v2/market/ticker?symbol={s}_SPBL"
        r1 = requests.get(url1, timeout=10).json()
        data1 = r1.get("data", [])
        if data1 and isinstance(data1, dict) and "lastPr" in data1:
            return float(data1["lastPr"])

        # Резерв: Binance
        url2 = f"https://api.binance.com/api/v3/ticker/price?symbol={s.replace('/', '')}"
        r2 = requests.get(url2, timeout=10).json()
        if "price" in r2:
            return float(r2["price"])

        print(f"⚠️ Не удалось получить цену для {symbol}")
        return None
    except Exception as e:
        print(f"⚠️ Ошибка получения цены для {symbol}: {e}")
        return None

# === Получение максимумов и минимумов ===
def get_candles(symbol, interval, limit=200):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol.replace('/', '')}&interval={interval}&limit={limit}"
        data = requests.get(url, timeout=10).json()
        highs = [float(c[2]) for c in data]
        lows = [float(c[3]) for c in data]
        return max(highs), min(lows)
    except Exception as e:
        print(f"⚠️ Ошибка свечей для {symbol} ({interval}): {e}")
        return None, None

# === Проверка уровней ===
def check_levels():
    for pair in PAIRS:
        price = get_price(pair)
        if not price:
            continue

        max_1h, min_1h = get_candles(pair, "1h")
        max_12h, min_12h = get_candles(pair, "12h")
        max_24h, min_24h = get_candles(pair, "1d")

        if not all([max_1h, min_1h, max_12h, min_12h, max_24h, min_24h]):
            continue

        utc_now = datetime.utcnow() + timedelta(hours=UTC_OFFSET)
        time_now = utc_now.strftime("%H:%M (UTC+1)")

        # Проверка близости к уровням
        for tf, high, low in [
            ("1h", max_1h, min_1h),
            ("12h", max_12h, min_12h),
            ("24h", max_24h, min_24h)
        ]:
            dist_high = (high - price) / price * 100
            dist_low = (price - low) / price * 100

            if 0 < dist_high <= 0.1:
                msg = f"⚠️ {pair}\nТФ: {tf}\nЦена: {price}\nБлизко к MAX ({high})\nДистанция: {dist_high:.2f}%\n🕐 {time_now}"
                bot.send_message(TELEGRAM_CHAT_ID, msg)

            elif 0 < dist_low <= 0.1:
                msg = f"⚠️ {pair}\nТФ: {tf}\nЦена: {price}\nБлизко к MIN ({low})\nДистанция: {dist_low:.2f}%\n🕐 {time_now}"
                bot.send_message(TELEGRAM_CHAT_ID, msg)

        print(f"Проверена пара {pair}: {price}")

# === Команда /start ===
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        f"✅ Бот активен. Проверяю уровни по всем валютным парам каждые {CHECK_INTERVAL} секунд."
    )
    while True:
        check_levels()
        time.sleep(CHECK_INTERVAL)

# === Запуск ===
if __name__ == "__main__":
    print("🧹 Удаляю старый вебхук перед запуском...")
    try:
        resp = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook")
        print("Ответ Telegram:", resp.json())
    except Exception as e:
        print("⚠️ Не удалось удалить вебхук:", e)

    print("🚀 Бот запущен. Ожидает /start в Telegram.")
    bot.polling(non_stop=True, skip_pending=True)
