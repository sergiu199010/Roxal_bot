import os
import time
import ccxt
import logging
from telegram import Bot

# =============== НАСТРОЙКИ ===============
logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
EXCHANGE_NAME = os.getenv("EXCHANGE", "oanda").lower()  # можно fxcm или forexcom
POLL_SEC = int(os.getenv("POLL_SEC", "60"))  # проверка каждую минуту
THRESHOLD = float(os.getenv("THRESHOLD", "0.003"))  # 0.003 = 0.3 %

# Список валютных пар (как на Pocket Option)
PAIRS = [
    "EUR/USD",
    "GBP/AUD",
    "GBP/CHF",
    "GBP/USD",
    "USD/CHF",
    "USD/JPY",
    "GBP/CAD",
    "AUD/CAD",
    "AUD/USD",
    "USD/CAD",
    "GBP/JPY",
    "EUR/JPY",
    "AUD/CHF",
    "AUD/JPY",
    "CAD/CHF",
    "CAD/JPY",
    "CHF/JPY",
    "EUR/AUD",
    "EUR/CAD",
    "EUR/CHF",
    "EUR/GBP"
]
# ==========================================

exchange = getattr(ccxt, EXCHANGE_NAME)()
bot = Bot(token=TELEGRAM_TOKEN)
sent_signals = {}  # чтобы не спамил одинаковыми сигналами

def percent_diff(a, b):
    return abs(a - b) / b if b != 0 else 0

def check_levels(symbol, timeframe, limit, name):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if not ohlcv:
            return None
        closes = [c[4] for c in ohlcv]
        high = max(closes)
        low = min(closes)
        current = closes[-1]

        # Проверка близости к максимуму / минимуму
        if current >= high * (1 - THRESHOLD):
            return f"🚀 {symbol} близко к максимуму за {name}\nЦена: {current:.5f} | High: {high:.5f}"
        elif current <= low * (1 + THRESHOLD):
            return f"🔻 {symbol} близко к минимуму за {name}\nЦена: {current:.5f} | Low: {low:.5f}"
    except Exception as e:
        logging.warning(f"{symbol} ({name}) ошибка: {e}")
    return None

def main():
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🤖 Бот запущен. Проверяю пары каждые 60 сек...")
    while True:
        for symbol in PAIRS:
            for timeframe, name, limit in [
                ("5m", "1 час", 12),
                ("5m", "12 часов", 144),
                ("5m", "24 часа", 288)
            ]:
                signal = check_levels(symbol, timeframe, limit, name)
                key = f"{symbol}-{name}"
                if signal:
                    if sent_signals.get(key) != signal:
                        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=signal)
                        sent_signals[key] = signal
                        logging.info(signal)
                else:
                    sent_signals.pop(key, None)
        time.sleep(POLL_SEC)

if __name__ == "__main__":
    main()
