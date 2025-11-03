import os
import time
import telebot
import requests
from datetime import datetime, timedelta

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API_KEY = os.getenv("API_KEY")  # ключ от APIlayer

bot = telebot.TeleBot(TOKEN)

# Валютные пары
PAIRS = [
    "EUR/USD", "GBP/AUD", "GBP/CHF", "GBP/USD", "USD/CHF", "USD/JPY",
    "GBP/CAD", "AUD/CAD", "AUD/USD", "USD/CAD", "GBP/JPY", "EUR/JPY",
    "AUD/CHF", "AUD/JPY", "CAD/CHF", "CAD/JPY", "CHF/JPY", "EUR/AUD",
    "EUR/CAD", "EUR/CHF", "EUR/GBP"
]

UTC_OFFSET = 1  # часовой пояс UTC+1
CHECK_INTERVAL = 60  # секунд

# Получение котировки через APIlayer
def get_price(pair):
    try:
        base, quote = pair.split('/')
        url = f"https://api.apilayer.com/exchangerates_data/convert?from={base}&to={quote}&amount=1"
        headers = {"apikey": API_KEY}
        r = requests.get(url, headers=headers)
        data = r.json()
        if "result" in data:
            return float(data["result"])
        else:
            print(f"⚠️ Ошибка получения цены для {pair}: {data}")
            return None
    except Exception as e:
        print(f"⚠️ Ошибка при запросе {pair}: {e}")
        return None

# Имитация уровней (в реальном варианте можно подключить исторические данные)
def get_levels(pair):
    price = get_price(pair)
    if price is None:
        return None, None, None
    # Пример расчета уровней
    max_lvl = price * 1.001
    min_lvl = price * 0.999
    return min_lvl, max_lvl, price

def check_levels():
    for pair in PAIRS:
        levels = get_levels(pair)
        if not levels:
            continue
        min_lvl, max_lvl, price = levels
        dist_min = (price - min_lvl) / price * 100
        dist_max = (max_lvl - price) / price * 100

        if dist_min < 0.08:
            send_signal(pair, "MIN", price, min_lvl, dist_min)
        elif dist_max < 0.08:
            send_signal(pair, "MAX", price, max_lvl, dist_max)
        else:
            print(f"⏳ {pair} | Цена: {price:.5f}")

def send_signal(pair, level_type, price, level, distance):
    now = datetime.utcnow() + timedelta(hours=UTC_OFFSET)
    msg = (
        f"⚠️ {pair}\n"
        f"ТФ: 1h\n"
        f"Цена: {price:.5f}\n"
        f"Близко к {level_type} ({level:.5f})\n"
        f"Дистанция: {distance:.2f}%\n"
        f"🕐 {now.strftime('%H:%M')} (UTC+{UTC_OFFSET})"
    )
    bot.send_message(CHAT_ID, msg)
    print(msg)

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, f"✅ Бот активен. Проверяю уровни по всем валютным парам каждые {CHECK_INTERVAL} секунд.")
    while True:
        check_levels()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    print("🚀 Бот запущен. Ожидает /start в Telegram.")
    bot.infinity_polling()
