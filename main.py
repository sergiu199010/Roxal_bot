import os
import time
import telebot
import requests
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot = telebot.TeleBot(TOKEN)

PAIRS = [
    "EUR/USD", "GBP/AUD", "GBP/CHF", "GBP/USD", "USD/CHF", "USD/JPY",
    "GBP/CAD", "AUD/CAD", "AUD/USD", "USD/CAD", "GBP/JPY", "EUR/JPY",
    "AUD/CHF", "AUD/JPY", "CAD/CHF", "CAD/JPY", "CHF/JPY", "EUR/AUD",
    "EUR/CAD", "EUR/CHF", "EUR/GBP"
]

def get_price(pair):
    base, quote = pair.split("/")
    try:
        url = f"https://api.bitget.com/api/v2/market/history-candles?symbol={base}{quote}_SPBL&granularity=60"
        data = requests.get(url, timeout=10).json().get("data", [])
        if not data:
            return None
        candles = [(float(c[1]), float(c[2])) for c in data[:1440]]
        current = float(data[0][4])
        return {
            "current": current,
            "high_1h": max(h for _, h in candles[:60]),
            "low_1h": min(l for l, _ in candles[:60]),
            "high_12h": max(h for _, h in candles[:720]),
            "low_12h": min(l for l, _ in candles[:720]),
            "high_24h": max(h for _, h in candles[:1440]),
            "low_24h": min(l for l, _ in candles[:1440]),
        }
    except Exception:
        return None

@bot.message_handler(commands=["start"])
def start_message(message):
    global CHAT_ID
    CHAT_ID = str(message.chat.id)
    bot.send_message(
        CHAT_ID,
        "✅ Бот активен и будет присылать сигналы, когда цена близка "
        "к максимуму или минимуму по 1h, 12h и 24h."
    )

def check_levels():
    if not CHAT_ID:
        print("Нет chat_id. Отправь /start своему боту для регистрации.")
        return
    for pair in PAIRS:
        data = get_price(pair)
        if not data:
            continue
        price = data["current"]
        for tf, high, low in [
            ("1h", data["high_1h"], data["low_1h"]),
            ("12h", data["high_12h"], data["low_12h"]),
            ("24h", data["high_24h"], data["low_24h"]),
        ]:
            dist_high = abs((high - price) / high) * 100
            dist_low = abs((price - low) / low) * 100
            if dist_high < 0.1:
                bot.send_message(CHAT_ID, f"⚠️ {pair}\nТФ: {tf}\nЦена: {price:.5f}\nБлизко к MAX ({high:.5f})\nДистанция: {dist_high:.2f}%\n🕐 {datetime.utcnow().strftime('%H:%M')} (UTC+1)")
            elif dist_low < 0.1:
                bot.send_message(CHAT_ID, f"⚠️ {pair}\nТФ: {tf}\nЦена: {price:.5f}\nБлизко к MIN ({low:.5f})\nДистанция: {dist_low:.2f}%\n🕐 {datetime.utcnow().strftime('%H:%M')} (UTC+1)")

def main_loop():
    while True:
        check_levels()
        time.sleep(55)

if __name__ == "__main__":
    print("Удаляю webhook перед запуском polling...")
    try:
        bot.remove_webhook()
    except Exception:
        pass
    print("Бот запущен. Ожидает /start в Telegram.")
    bot.polling(non_stop=True, skip_pending=True)
    main_loop()
