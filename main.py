import os
import time
import requests
import telebot
import asyncio
from datetime import datetime, timedelta

# === Настройки ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
EXCHANGE = os.getenv("EXCHANGE", "bitget")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# === Валютные пары ===
PAIRS = [
    "EUR/USD", "GBP/AUD", "GBP/CHF", "GBP/USD", "USD/CHF", "USD/JPY",
    "GBP/CAD", "AUD/CAD", "AUD/USD", "USD/CAD", "GBP/JPY", "EUR/JPY",
    "AUD/CHF", "AUD/JPY", "CAD/CHF", "CAD/JPY", "CHF/JPY", "EUR/AUD",
    "EUR/CAD", "EUR/CHF", "EUR/GBP"
]

# === Функция получения котировок с Bitget ===
def get_price(symbol):
    try:
        s = symbol.replace("/", "")
        url = f"https://api.bitget.com/api/v2/market/tickers?symbol={s}"
        r = requests.get(url, timeout=10).json()
        data = r.get("data", [])
        if not data:
            return None
        return float(data[0]["lastPr"])
    except Exception:
        return None

# === Исторические данные (для определения уровней) ===
def get_ohlc(symbol, period):
    try:
        s = symbol.replace("/", "")
        url = f"https://api.bitget.com/api/v2/market/candles?symbol={s}&granularity={period}"
        r = requests.get(url, timeout=10).json()
        candles = r.get("data", [])
        prices = [float(c[4]) for c in candles]  # закрытия
        return prices
    except Exception:
        return []

# === Проверка уровней ===
def check_levels(symbol):
    price = get_price(symbol)
    if not price:
        return None

    levels = []
    for period, name in [(86400, "24h"), (43200, "12h"), (3600, "1h")]:
        prices = get_ohlc(symbol, period)
        if prices:
            low = min(prices)
            high = max(prices)
            if price >= high * 0.999:  # близко к максимуму
                levels.append((name, "MAX", high, price))
            elif price <= low * 1.001:  # близко к минимуму
                levels.append((name, "MIN", low, price))
    return levels

# === Отправка сигнала ===
def send_signal(symbol, levels):
    utc_time = datetime.utcnow() + timedelta(hours=1)
    for name, pos, level, price in levels:
        msg = (
            f"⚠️ {symbol}\n"
            f"ТФ: {name}\n"
            f"Цена: {price:.5f}\n"
            f"Близко к {pos} ({level:.5f})\n"
            f"🕐 {utc_time.strftime('%H:%M')} (UTC+1)"
        )
        bot.send_message(TELEGRAM_CHAT_ID, msg)

# === Цикл проверки сигналов ===
async def check_signals():
    while True:
        for pair in PAIRS:
            levels = check_levels(pair)
            if levels:
                send_signal(pair, levels)
            await asyncio.sleep(2)  # чтобы не перегружать API
        await asyncio.sleep(55)  # повтор цикла

# === Команда /start ===
@bot.message_handler(commands=['start'])
def start_message(message):
    bot.reply_to(message, "✅ Бот активен. Проверяю уровни по всем валютным парам каждые 55 секунд.")

# === Запуск ===
if __name__ == "__main__":
    bot.remove_webhook()
    print("Удаляю вебхук перед запуском polling...")

    loop = asyncio.get_event_loop()
    loop.create_task(check_signals())

    print("Бот запущен. Ожидает /start в Telegram.")
    bot.polling(non_stop=True, skip_pending=True)
