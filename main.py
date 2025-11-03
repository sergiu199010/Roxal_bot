#!/usr/bin/env python3
# main.py — Roxal_bot (уровни: 30m,1h,3h,6h,12h)

import requests
import time
import telebot
from datetime import datetime, timedelta
import logging

# --- Telegram ---
BOT_TOKEN = "8550877857:AAG4Mt1lbBW-bPPvbIRodhDjvMq9iVIkr-0"  # твой токен
CHAT_ID = "YOUR_CHAT_ID"  # замени на свой Chat ID
bot = telebot.TeleBot(BOT_TOKEN)

# --- Список пар (Pocket Option) ---
PAIRS = [
    "EUR/USD", "GBP/AUD", "GBP/CHF", "GBP/USD", "USD/CHF", "USD/JPY",
    "GBP/CAD", "AUD/CAD", "AUD/USD", "USD/CAD", "GBP/JPY", "EUR/JPY",
    "AUD/CHF", "AUD/JPY", "CAD/CHF", "CAD/JPY", "CHF/JPY", "EUR/AUD",
    "EUR/CAD", "EUR/CHF", "EUR/GBP"
]

# --- Настройки ---
INTERVAL = 30  # секунд между циклами
TIMEFRAMES = [30, 60, 180, 360, 720]  # в минутах (30m,1h,3h,6h,12h)
API_KEY = "44c2037f787ac7ae858bc983"
BASE_URL = "https://api.exchangerate.host"

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(message)s")

# --- Получение цены ---
def get_price(pair):
    try:
        base, quote = pair.split("/")
        response = requests.get(f"{BASE_URL}/latest", params={"base": base, "symbols": quote})
        data = response.json()
        return float(data["rates"][quote])
    except Exception as e:
        logging.error(f"Ошибка получения цены {pair}: {e}")
        return None

# --- Исторические данные ---
def get_historical_data(pair, minutes):
    try:
        base, quote = pair.split("/")
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=minutes)
        response = requests.get(
            f"{BASE_URL}/timeseries",
            params={
                "base": base,
                "symbols": quote,
                "start_date": start_time.strftime("%Y-%m-%d"),
                "end_date": end_time.strftime("%Y-%m-%d")
            },
        )
        data = response.json()
        if "rates" not in data:
            return []
        prices = [v[quote] for v in data["rates"].values()]
        return prices
    except Exception as e:
        logging.error(f"Ошибка исторических данных {pair}: {e}")
        return []

# --- Проверка уровней ---
def check_levels(pair):
    current_price = get_price(pair)
    if not current_price:
        return None

    signals = []
    for m in TIMEFRAMES:
        history = get_historical_data(pair, m)
        if not history:
            continue
        low, high = min(history), max(history)
        if current_price >= high * 0.998:
            signals.append(f"⬆ {pair} близко к максимуму {m}m ({current_price:.5f})")
        elif current_price <= low * 1.002:
            signals.append(f"⬇ {pair} близко к минимуму {m}m ({current_price:.5f})")
    return signals

# --- Отправка сигнала ---
def send_signal(msg):
    try:
        bot.send_message(CHAT_ID, msg)
    except Exception as e:
        logging.error(f"Ошибка отправки в Telegram: {e}")

# --- Основной цикл ---
def main():
    bot.send_message(CHAT_ID, "✅ Roxal_bot активен (30m,1h,3h,6h,12h).")
    while True:
        for pair in PAIRS:
            signals = check_levels(pair)
            if signals:
                send_signal(
                    f"📊 {pair}\n" + "\n".join(signals) +
                    f"\n────────────\n⏰ {datetime.utcnow().strftime('%H:%M:%S')} UTC"
                )
            time.sleep(1)
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
