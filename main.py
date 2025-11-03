import time
import datetime
import pytz
import yfinance as yf
import telebot
import os

# ==================== НАСТРОЙКИ ====================
TELEGRAM_TOKEN = "8175185892:AAFgwnRnjW_URksiHNq7TyPzyozGYz2CjS8"
CHECK_INTERVAL = 55  # Проверка каждые 55 секунд
TIMEZONE = pytz.timezone("Etc/GMT-1")  # UTC+1 (GMT-1 в pytz — это +1 к UTC)
PERCENT_THRESHOLD = 0.15  # На сколько % от минимума/максимума считается "близко"

# Список валютных пар с Pocket Option
PAIRS = [
    "EUR/USD", "GBP/AUD", "GBP/CHF", "GBP/USD", "USD/CHF", "USD/JPY",
    "GBP/CAD", "AUD/CAD", "AUD/USD", "USD/CAD", "GBP/JPY", "EUR/JPY",
    "AUD/CHF", "AUD/JPY", "CAD/CHF", "CAD/JPY", "CHF/JPY", "EUR/AUD",
    "EUR/CAD", "EUR/CHF", "EUR/GBP"
]

# Преобразуем в формат Yahoo Finance (пример: EURUSD=X)
YF_SYMBOLS = {p: p.replace("/", "") + "=X" for p in PAIRS}

# ==================== TELEGRAM ====================
bot = telebot.TeleBot(TELEGRAM_TOKEN)
CHAT_IDS_FILE = "chat_ids.txt"


def load_chat_ids():
    if os.path.exists(CHAT_IDS_FILE):
        with open(CHAT_IDS_FILE, "r") as f:
            return [int(x.strip()) for x in f if x.strip()]
    return []


def save_chat_id(chat_id):
    ids = load_chat_ids()
    if chat_id not in ids:
        ids.append(chat_id)
        with open(CHAT_IDS_FILE, "w") as f:
            f.write("\n".join(map(str, ids)))


def send_message(chat_id, text):
    try:
        bot.send_message(chat_id, text)
    except Exception as e:
        print(f"[Telegram ERROR]: {e}")


@bot.message_handler(commands=["start"])
def start_command(message):
    save_chat_id(message.chat.id)
    bot.send_message(
        message.chat.id,
        "✅ Бот активен и будет присылать сигналы, когда цена близка к максимуму или минимуму по 1h, 12h и 24h."
    )


# ==================== АНАЛИЗ КОТИРОВОК ====================
def get_data(symbol, period):
    try:
        df = yf.download(
            tickers=symbol,
            period=period,
            interval="5m",
            progress=False,
            threads=False
        )
        if df.empty:
            print(f"[DATA] Пусто для {symbol}")
            return None
        return df
    except Exception as e:
        print(f"[ERROR загрузки {symbol}]: {e}")
        return None


def check_levels(pair, symbol, chat_ids):
    tf_periods = {
        "1h": "2d",
        "12h": "5d",
        "24h": "10d"
    }

    for tf, period in tf_periods.items():
        df = get_data(symbol, period)
        if df is None or len(df) < 10:
            continue

        current = df["Close"].iloc[-1]
        max_price = df["High"].max()
        min_price = df["Low"].min()

        distance_to_max = abs((max_price - current) / max_price) * 100
        distance_to_min = abs((current - min_price) / min_price) * 100

        if distance_to_max <= PERCENT_THRESHOLD:
            direction = "Близко к MAX"
            target = max_price
            distance = distance_to_max
        elif distance_to_min <= PERCENT_THRESHOLD:
            direction = "Близко к MIN"
            target = min_price
            distance = distance_to_min
        else:
            continue

        now = datetime.datetime.now(TIMEZONE).strftime("%H:%M")
        text = (
            f"⚠️ {pair}\n"
            f"ТФ: {tf}\n"
            f"Цена: {current:.5f}\n"
            f"{direction} ({target:.5f})\n"
            f"Дистанция: {distance:.2f}%\n"
            f"🕐 {now} (UTC+1)"
        )

        print(text)
        for cid in chat_ids:
            send_message(cid, text)


# ==================== ОСНОВНОЙ ЦИКЛ ====================
def main():
    print("=== FX Levels Bot started ===")
    chat_ids = load_chat_ids()
    if not chat_ids:
        print("Нет chat.id. Отправь /start своему боту в Telegram.")

    while True:
        chat_ids = load_chat_ids()
        for pair, symbol in YF_SYMBOLS.items():
            check_levels(pair, symbol, chat_ids)
            time.sleep(1)  # небольшая пауза между запросами

        print(f"Проверка завершена — ожидание {CHECK_INTERVAL} секунд...\n")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: bot.polling(none_stop=True)).start()
    main()
