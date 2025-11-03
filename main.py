# main.py
import os
import time
import threading
import datetime
import pytz
from flask import Flask, request
import telebot
import yfinance as yf
import pandas as pd

# ==================== НАСТРОЙКИ ====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8175185892:AAFgwnRnjW_URksiHNq7TyPzyozGYz2CjS8")
CHECK_INTERVAL = 55  # секунд
TIMEZONE = pytz.timezone("Etc/GMT-1")  # UTC+1 (в pytz знак обратный)
PERCENT_THRESHOLD = 0.15  # % расстояния до min/max для сигнала (0.15 => 0.15%)
# Примечание: если захочешь 0.2% — измени на 0.2

# Валютные пары (только валюты по твоему запросу)
PAIRS = [
    "EUR/USD", "GBP/AUD", "GBP/CHF", "GBP/USD", "USD/CHF", "USD/JPY",
    "GBP/CAD", "AUD/CAD", "AUD/USD", "USD/CAD", "GBP/JPY", "EUR/JPY",
    "AUD/CHF", "AUD/JPY", "CAD/CHF", "CAD/JPY", "CHF/JPY", "EUR/AUD",
    "EUR/CAD", "EUR/CHF", "EUR/GBP"
]

# Преобразование в тикеры Yahoo Finance (пример: EURUSD=X)
YF_SYMBOLS = {p: p.replace("/", "") + "=X" for p in PAIRS}

# Файлы
CHAT_IDS_FILE = "chat_ids.txt"

# Flask + bot
app = Flask(__name__)
bot = telebot.TeleBot(TELEGRAM_TOKEN)


# ==================== Telegram / chat_id utils ====================
def load_chat_ids():
    if os.path.exists(CHAT_IDS_FILE):
        with open(CHAT_IDS_FILE, "r", encoding="utf-8") as f:
            return [int(x.strip()) for x in f if x.strip()]
    return []


def save_chat_id(chat_id):
    ids = load_chat_ids()
    if chat_id not in ids:
        ids.append(chat_id)
        with open(CHAT_IDS_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(map(str, ids)))


def send_message(chat_id, text):
    try:
        bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception as e:
        print(f"[Telegram ERROR] {e}")


@bot.message_handler(commands=["start"])
def start_command(message):
    save_chat_id(message.chat.id)
    bot.send_message(
        message.chat.id,
        "✅ Бот активен и будет присылать сигналы, когда цена близка к максимуму или минимуму по 1h, 12h и 24h."
    )


# ==================== Webhook endpoint ====================
# Telegram будет отправлять POST на /{TELEGRAM_TOKEN}
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    try:
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception as e:
        print("Webhook processing error:", e)
    return "", 200


# ==================== Загрузка данных и логика уровней ====================
def get_history(symbol: str, period: str):
    try:
        df = yf.download(
            tickers=symbol,
            period=period,
            interval="5m",
            progress=False,
            threads=False
        )
        if df is None or df.empty:
            print(f"[DATA] Пусто для {symbol} (period={period})")
            return None
        # убедимся, что есть нужные колонки
        if "Close" not in df.columns or "High" not in df.columns or "Low" not in df.columns:
            return None
        return df.dropna()
    except Exception as e:
        print(f"[ERROR загрузки {symbol}]: {e}")
        return None


def pct_distance(a, b):
    try:
        return abs((a - b) / b) * 100
    except Exception:
        return 999.0


def check_levels_and_alert(chat_ids):
    """
    Проходим по парам и таймфреймам, если близко к MIN или MAX — отправляем сигнал.
    """
    tf_periods = {
        "1h": "2d",
        "12h": "5d",
        "24h": "10d"
    }

    for pair, symbol in YF_SYMBOLS.items():
        try:
            # Получаем последние тикеры (общее для всех TF — можно оптимизировать)
            # но для простоты просто запрашиваем по каждому TF свой период
            current_price = None
            alerted = False

            for tf, period in tf_periods.items():
                df = get_history(symbol, period)
                if df is None or len(df) < 5:
                    continue

                current = float(df["Close"].iloc[-1])
                max_price = float(df["High"].max())
                min_price = float(df["Low"].min())

                dist_to_max = pct_distance(max_price, current)
                dist_to_min = pct_distance(current, min_price)

                # Точность и условие
                if dist_to_max <= PERCENT_THRESHOLD:
                    direction = "Близко к MAX"
                    target = max_price
                    distance = dist_to_max
                elif dist_to_min <= PERCENT_THRESHOLD:
                    direction = "Близко к MIN"
                    target = min_price
                    distance = dist_to_min
                else:
                    continue

                # Формируем сообщение в нужном формате
                now = datetime.datetime.now(TIMEZONE).strftime("%H:%M")
                text = (
                    f"⚠️ {pair}\n"
                    f"ТФ: {tf}\n"
                    f"Цена: {current:.5f}\n"
                    f"{direction} ({target:.5f})\n"
                    f"Дистанция: {distance:.2f}%\n"
                    f"🕐 {now} (UTC+1)"
                )

                print("ALERT:", text)
                for cid in chat_ids:
                    send_message(cid, text)

                alerted = True
                # Если по этой паре уже отправили сигнал для одного TF — можно продолжать и по другим TF (по желанию)
                # здесь мы не останавливаемся, чтобы слать сигналы и для других TF тоже
            time.sleep(0.5)  # чтобы не перегружать yfinance
        except Exception as e:
            print(f"[ERROR] {pair}/{symbol}: {e}")


# ==================== Фоновый цикл проверки ====================
def background_loop():
    print("Background price-check loop started.")
    while True:
        chat_ids = load_chat_ids()
        if not chat_ids:
            print("Нет chat_id. Отправь /start своему боту для регистрации.")
        else:
            check_levels_and_alert(chat_ids)
        print(f"Пауза {CHECK_INTERVAL} сек...\n")
        time.sleep(CHECK_INTERVAL)


# ==================== Старт приложения ====================
def set_webhook():
    webhook_url_base = os.environ.get("WEBHOOK_URL")
    if not webhook_url_base:
        print("ERROR: WEBHOOK_URL не установлен в переменных окружения.")
        return False
    full_url = webhook_url_base.rstrip("/") + f"/{TELEGRAM_TOKEN}"
    try:
        bot.remove_webhook()
    except Exception:
        pass
    time.sleep(0.5)
    ok = bot.set_webhook(url=full_url)
    if ok:
        print(f"Webhook установлен: {full_url}")
    else:
        print("Не удалось установить webhook.")
    return ok


if __name__ == "__main__":
    # Устанавливаем webhook
    set_webhook()

    # Запускаем фон. цикл в отдельном потоке
    t = threading.Thread(target=background_loop, daemon=True)
    t.start()

    # Запускаем Flask (Render будет проксировать https запросы сюда)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
