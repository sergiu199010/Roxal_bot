#!/usr/bin/env python3
# main.py — Roxal_bot (уровни: 30m,1h,3h,6h,12h)

import requests
import time
import telebot
from datetime import datetime, timedelta
import logging

# --- Telegram ---
BOT_TOKEN = "8175185892:AAHSGqGTcHhDNGYS84uBVupU8Ci9KA5496g"
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

def get_price(pair):
    try:
        base, quote = pair.split("/")
        response = requests.get(f"{BASE_URL}/latest", params={"base": base, "symbols": quote})
        data = response.json()
        return float(data["rates"][quote])
    except Exception as e:
        logging.error(f"Ошибка получения цены {pair}: {e}")
        return None

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

def check_levels(pair):
    current_price = get_price(pair)
    if not current_price:
