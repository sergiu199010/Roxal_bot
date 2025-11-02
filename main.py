import os
import asyncio
import pandas as pd
import ccxt
from telegram import Bot

# === Читаем переменные окружения ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SYMBOL = os.getenv("SYMBOL", "BTC/USDT")
EXCHANGE_NAME = os.getenv("EXCHANGE", "binance")
THRESHOLD = float(os.getenv("THRESHOLD", 0.001))
POLL_SEC = int(os.getenv("POLL_SEC", 30))
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", 900))

# === Проверка обязательных переменных ===
if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("❌ Не найдены TELEGRAM_TOKEN или TELEGRAM_CHAT_ID. Добавь их в Railway Variables.")

# === Настройка бота и биржи ===
bot = Bot(TELEGRAM_TOKEN)
exchange = getattr(ccxt, EXCHANGE_NAME)()

print("✅ Бот запущен. Ожидание сигналов...")

# === Функция для отправки сообщений в Telegram ===
async def send_message(text):
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
    except Exception as e:
        print(f"Ошибка при отправке сообщения: {e}")

# === Основная логика ===
async def check_levels():
    last_signal_time = None

    while True:
        try:
            # Загружаем 5-минутные свечи за последние 24 часа
            ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe="5m", limit=288)
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

            # Вычисляем уровни High/Low
            high_1h = df["high"].tail(12).max()   # последние 12 свечей = 1 час
            low_1h = df["low"].tail(12).min()
            high_12h = df["high"].tail(12 * 12).max()
            low_12h = df["low"].tail(12 * 12).min()
            high_24h = df["high"].max()
            low_24h = df["low"].min()

            current_price = df["close"].iloc[-1]

            # Проверяем касание уровней
            levels = {
                "1h High": high_1h,
                "1h Low": low_1h,
                "12h High": high_12h,
                "12h Low": low_12h,
                "24h High": high_24h,
                "24h Low": low_24h
            }

            for name, level in levels.items():
                if abs(current_price - level) / level <= THRESHOLD:
                    now = pd.Timestamp.now()
                    if not last_signal_time or (now - last_signal_time).total_seconds() > COOLDOWN_SEC:
                        message = f"📊 {SYMBOL}\nКасание уровня {name}\nЦена: {current_price:.2f}\nУровень: {level:.2f}"
                        await send_message(message)
                        print(f"📤 Отправлен сигнал: {message}")
                        last_signal_time = now

        except Exception as e:
            print(f"⚠️ Ошибка: {e}")

        await asyncio.sleep(POLL_SEC)

# === Запуск ===
async def main():
    await check_levels()

if __name__ == "__main__":
    asyncio.run(main())
