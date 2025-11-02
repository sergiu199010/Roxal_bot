import os
import time
import ccxt
import logging
from telegram import Bot

# ---------- НАСТРОЙКИ ----------
logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
EXCHANGE_NAME = os.getenv("EXCHANGE", "oanda").lower()  # источники форекс котировок
POLL_SEC = int(os.getenv("POLL_SEC", "60"))  # проверка каждую минуту

# Основные активы Pocket Option (аналогичные тикеры на биржах)
PAIRS = [
    # Forex
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
    "USD/CHF", "NZD/USD", "EUR/GBP", "EUR/JPY", "GBP/JPY",
    # Commodities
    "XAU/USD",  # золото
    "XAG/USD",  # серебро
    "USOIL/USD", "UKOIL/USD",
    # Crypto
    "BTC/USDT", "ETH/USDT", "LTC/USDT", "XRP/USDT", "DOGE/USDT",
    # Индексы (эмуляция)
    "SPX/USD", "NAS100/USD", "DAX40/EUR"
]
# -------------------------------

# Подключаем биржу и Telegram
exchange = getattr(ccxt, EXCHANGE_NAME)()
bot = Bot(token=TELEGRAM_TOKEN)
sent_signals = {}  # чтобы не слал одно и то же

def get_signal(symbol, timeframe, limit, name):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if not ohlcv:
            return None

        closes = [c[4] for c in ohlcv]
        high = max(closes)
        low = min(closes)
        current = closes[-1]

        if current >= high * 0.995:  # ближе 0.5% к максимуму
            return f"🚀 {symbol}: приближается к максимуму {high:.5f} ({name})\nТекущая: {current:.5f}"
        elif current <= low * 1.005:  # ближе 0.5% к минимуму
            return f"🔻 {symbol}: приближается к минимуму {low:.5f} ({name})\nТекущая: {current:.5f}"
    except Exception as e:
        logging.error(f"{symbol} ({name}) ошибка: {e}")
    return None

def main():
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🤖 Бот запущен. Проверяю активы Pocket Option каждые 60 сек...")
    time.sleep(3)
    while True:
        for symbol in PAIRS:
            for timeframe, name, limit in [
                ("5m", "1h", 12),
                ("5m", "12h", 144),
                ("5m", "24h", 288)
            ]:
                signal = get_signal(symbol, timeframe, limit, name)
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
