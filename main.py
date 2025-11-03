import requests
import time
import telebot
from datetime import datetime, timedelta

# --- Telegram ---
BOT_TOKEN = "8550877857:AAG4Mt1lbBW-bPPvbIRodhDjvMq9iVIkr-0"
CHAT_ID = "YOUR_CHAT_ID"  # вставь свой chat id сюда
bot = telebot.TeleBot(BOT_TOKEN)

# --- Пары (Pocket Option) ---
PAIRS = [
    "EUR/USD", "GBP/AUD", "GBP/CHF", "GBP/USD", "USD/CHF", "USD/JPY",
    "GBP/CAD", "AUD/CAD", "AUD/USD", "USD/CAD", "GBP/JPY", "EUR/JPY",
    "AUD/CHF", "AUD/JPY", "CAD/CHF", "CAD/JPY", "CHF/JPY",
    "EUR/AUD", "EUR/CAD", "EUR/CHF", "EUR/GBP"
]

# --- Настройки ---
INTERVAL = 30  # секунд между циклами
TIMEFRAMES = [30, 60, 180, 360, 720]  # 30m, 1h, 3h, 6h, 12h
API_KEY = "44c2037f787ac7ae858bc983"
BASE_URL = "https://api.exchangerate.host"

def get_price(pair):
    """Текущая цена"""
    try:
        base, quote = pair.split("/")
        r = requests.get(f"{BASE_URL}/latest", params={"base": base, "symbols": quote}, timeout=10)
        js = r.json()
        return js["rates"][quote]
    except Exception as e:
        print(f"Ошибка цены {pair}: {e}")
        return None

def get_historical(pair, minutes):
    """История за X минут"""
    try:
        base, quote = pair.split("/")
        end = datetime.utcnow()
        start = end - timedelta(minutes=minutes)
        r = requests.get(
            f"{BASE_URL}/timeseries",
            params={
                "base": base,
                "symbols": quote,
                "start_date": start.strftime("%Y-%m-%d"),
                "end_date": end.strftime("%Y-%m-%d")
            },
            timeout=10
        )
        js = r.json()
        if "rates" not in js:
            return []
        return [v[quote] for v in js["rates"].values()]
    except Exception as e:
        print(f"Ошибка истории {pair}: {e}")
        return []

def check_levels(pair):
    """Проверка уровней"""
    cur = get_price(pair)
    if not cur:
        return []
    signals = []
    for tf in TIMEFRAMES:
        data = get_historical(pair, tf)
        if not data:
            continue
        low, high = min(data), max(data)
        if cur >= high * 0.998:
            signals.append(f"⬆ {pair} близко к максимуму {tf}m ({cur:.5f})")
        elif cur <= low * 1.002:
            signals.append(f"⬇ {pair} близко к минимуму {tf}m ({cur:.5f})")
    return signals

def send(msg):
    """Отправка в Telegram"""
    try:
        bot.send_message(CHAT_ID, msg)
    except Exception as e:
        print("Ошибка Telegram:", e)

def main():
    send("✅ Roxal_bot активен (30m,1h,3h,6h,12h)")
    while True:
        for pair in PAIRS:
            signals = check_levels(pair)
            if signals:
                send(
                    f"📊 {pair}\n" + "\n".join(signals) +
                    f"\n────────────\n⏰ {datetime.utcnow().strftime('%H:%M:%S')} UTC"
                )
            time.sleep(1)
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
