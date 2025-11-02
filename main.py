import os
import time
import ccxt
import logging
from telegram import Bot

logging.basicConfig(level=logging.INFO)

# Настройки окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
EXCHANGE_NAME = os.getenv("EXCHANGE", "binance").lower()
POLL_SEC = int(os.getenv("POLL_SEC", "600"))  # каждые 10 минут

# Подключение к бирже
exchange = getattr(ccxt, EXCHANGE_NAME)()
bot = Bot(token=TELEGRAM_TOKEN)

def get_signal(symbol, timeframe, lookback_hours):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=lookback_hours)
        if not ohlcv:
            return None

        closes = [c[4] for c in ohlcv]
        high = max(closes)
        low = min(closes)
        current = closes[-1]

        # Проверка на приближение к уровням
        if current >= high * 0.98:
            return f"🚀 {symbol} приближается к максимуму за {lookback_hours} свечей ({timeframe})"
        elif current <= low * 1.02:
            return f"🔻 {symbol} приближается к минимуму за {lookback_hours} свечей ({timeframe})"
    except Exception as e:
        logging.error(f"{symbol} ({timeframe}) — ошибка: {e}")
    return None

def main():
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🤖 Бот запущен. Ожидание сигналов...")
    tickers = list(exchange.load_markets().keys())[:20]

    while True:
        for symbol in tickers:
            for timeframe, hours in [("1h", 1), ("1h", 12), ("1h", 24)]:
                signal = get_signal(symbol, timeframe, hours)
                if signal:
                    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=signal)
                    logging.info(signal)
        time.sleep(POLL_SEC)

if __name__ == "__main__":
    main()
