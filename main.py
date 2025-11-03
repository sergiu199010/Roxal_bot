import os
import requests
import time
import telebot
from datetime import datetime
import pytz

CHECK_INTERVAL = 60
TIMEZONE = "UTC+1"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

PAIRS = [
    "EUR/USD", "GBP/AUD", "GBP/CHF", "GBP/USD", "USD/CHF", "USD/JPY",
    "GBP/CAD", "AUD/CAD", "AUD/USD", "USD/CAD", "GBP/JPY", "EUR/JPY",
    "AUD/CHF", "AUD/JPY", "CAD/CHF", "CAD/JPY", "CHF/JPY", "EUR/AUD",
    "EUR/CAD", "EUR/CHF", "EUR/GBP"
]

# === Функция получения цены с разных источников ===
def get_price(symbol):
    base, quote = symbol.split("/")
    variants = [
        f"{base}{quote}", f"{base}{quote}USDT", f"{base}-{quote}", f"{base}-{quote}-USD",
        f"{base}{quote}_SPBL", f"{base}{quote}_UMCBL"
    ]

    # --- Bitget ---
    for s in variants:
        try:
            r = requests.get("https://api.bitget.com/api/v2/market/ticker", params={"symbol": s}, timeout=3)
            data = r.json()
            if r.status_code == 200 and "data" in data and isinstance(data["data"], dict):
                price = float(data["data"].get("lastPr", 0))
                if price > 0:
                    return price
        except:
            pass

    # --- Binance ---
    for s in [f"{base}{quote}", f"{base}{quote}USDT"]:
        try:
            r = requests.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": s}, timeout=3)
            data = r.json()
            if r.status_code == 200 and "price" in data:
                return float(data["price"])
        except:
            pass

    # --- Coinbase ---
    for s in [f"{base}-{quote}", f"{base}-{quote}-USD"]:
        try:
            r = requests.get(f"https://api.exchange.coinbase.com/products/{s}/ticker", timeout=3)
            data = r.json()
            if r.status_code == 200 and "price" in data:
                return float(data["price"])
        except:
            pass

    print(f"⚠️ Не удалось получить цену для {symbol}")
    return None


def get_high_low(symbol, hours=24):
    price = get_price(symbol)
    if price:
        return price * 0.995, price * 1.005
    return None, None


def check_levels():
    tz = pytz.timezone("Europe/Berlin")
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


def test_token():
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe")
        if r.status_code == 200 and r.json().get("ok"):
            print("✅ Telegram токен действителен. Продолжаю запуск.")
            return True
    except Exception as e:
        print(f"❌ Ошибка проверки токена: {e}")
    return False


def main():
    if not test_token():
        print("❌ Неверный Telegram токен.")
        return

    try:
        print("🧹 Удаляю старый вебхук...")
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook")
    except:
        pass

    print("🚀 Бот запущен. Ожидает /start в Telegram.")

    @bot.message_handler(commands=["start"])
    def start(message):
        bot.reply_to(message, "✅ Бот активен. Проверяю уровни по всем валютным парам каждые 60 секунд.")
        while True:
            check_levels()
            time.sleep(CHECK_INTERVAL)

    bot.infinity_polling(timeout=10, long_polling_timeout=5)


if __name__ == "__main__":
    main()
