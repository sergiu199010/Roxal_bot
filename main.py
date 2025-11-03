import time
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import requests
import pandas as pd
import yfinance as yf
import pytz

# ==========================
# 🔧 НАСТРОЙКИ
# ==========================
TELEGRAM_TOKEN = "8550877857:AAG4Mt1lbBW-bPPvbIRodhDjvMq9iVIkr-0"
CHAT_IDS_FILE = "chat_ids.txt"          # сюда сохраняются chat_id
CHECK_INTERVAL_SEC = 60                 # как часто проверять (сек)
ALERT_COOLDOWN_MIN = 30                 # анти-спам: повтор не чаще, чем раз в N минут
DISTANCE_PCT = 0.2                      # близость к уровню в %, 0.2 = 0.2%
TZ_NAME = "Europe/Berlin"               # локальная зона для сообщений

# Список валютных пар и соответствие тикерам Yahoo Finance
PAIRS = [
    "EUR/USD", "GBP/AUD", "GBP/CHF", "GBP/USD", "USD/CHF",
    "USD/JPY", "GBP/CAD", "AUD/CAD", "AUD/USD", "USD/CAD",
    "GBP/JPY", "EUR/JPY", "AUD/CHF", "AUD/JPY", "CAD/CHF",
    "CAD/JPY", "CHF/JPY", "EUR/AUD", "EUR/CAD", "EUR/CHF", "EUR/GBP"
]

YF_SYMBOLS = {
    "EUR/USD": "EURUSD=X",
    "GBP/AUD": "GBPAUD=X",
    "GBP/CHF": "GBPCHF=X",
    "GBP/USD": "GBPUSD=X",
    "USD/CHF": "USDCHF=X",
    "USD/JPY": "USDJPY=X",
    "GBP/CAD": "GBPCAD=X",
    "AUD/CAD": "AUDCAD=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "USDCAD=X",
    "GBP/JPY": "GBPJPY=X",
    "EUR/JPY": "EURJPY=X",
    "AUD/CHF": "AUDCHF=X",
    "AUD/JPY": "AUDJPY=X",
    "CAD/CHF": "CADCHF=X",
    "CAD/JPY": "CADJPY=X",
    "CHF/JPY": "CHFJPY=X",
    "EUR/AUD": "EURAUD=X",
    "EUR/CAD": "EURCAD=X",
    "EUR/CHF": "EURCHF=X",
    "EUR/GBP": "EURGBP=X",
}

# Таймфреймы для уровней (в минутах)
WINDOWS_MINUTES = {
    "1h": 60,
    "12h": 12 * 60,
    "24h": 24 * 60,
}

# ==========================
# 📬 Telegram утилиты
# ==========================
def tg_api(method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    try:
        r = requests.post(url, data=payload, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[Telegram ERROR] {method}: {e}")
        return {}

def send_message(chat_id: int, text: str, disable_web_page_preview: bool = True) -> None:
    tg_api("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": disable_web_page_preview,
        "parse_mode": "HTML",
    })

def load_chat_ids() -> List[int]:
    if not os.path.exists(CHAT_IDS_FILE):
        return []
    try:
        with open(CHAT_IDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("chat_ids", [])
    except Exception:
        return []

def save_chat_ids(chat_ids: List[int]) -> None:
    with open(CHAT_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump({"chat_ids": chat_ids}, f, ensure_ascii=False, indent=2)

def fetch_new_chat_ids(chat_ids: List[int]) -> List[int]:
    try:
        resp = tg_api("getUpdates", {"timeout": 0})
        if not resp.get("ok"):
            return chat_ids
        for upd in resp.get("result", []):
            msg = upd.get("message") or upd.get("edited_message")
            if not msg:
                continue
            chat = msg.get("chat", {})
            cid = chat.get("id")
            if cid and cid not in chat_ids:
                chat_ids.append(cid)
        return chat_ids
    except Exception as e:
        print(f"[getUpdates ERROR] {e}")
        return chat_ids

def fetch_history(symbol: str, lookback_minutes: int) -> pd.DataFrame:
    df = yf.download(
        tickers=symbol,
        period="2d",
        interval="1m",
        progress=False,
        threads=False
    )
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.dropna()
    df = df.rename(columns=str.title)
    end_ts = df.index.max()
    start_ts = end_ts - pd.Timedelta(minutes=lookback_minutes)
    df = df.loc[df.index >= start_ts]
    return df

def compute_levels(df: pd.DataFrame, window_min: int) -> Tuple[float, float]:
    if df is None or df.empty:
        return (None, None)
    end_ts = df.index.max()
    start_ts = end_ts - pd.Timedelta(minutes=window_min)
    w = df.loc[df.index >= start_ts]
    if w.empty:
        return (None, None)
    return float(w["Low"].min()), float(w["High"].max())

def pct_distance(price: float, level: float) -> float:
    if price == 0 or level is None:
        return 999.0
    return abs(price - level) / price * 100.0

last_alert_at: Dict[Tuple[str, str, str], datetime] = {}

def can_alert(pair: str, tf: str, side: str, now_utc: datetime) -> bool:
    key = (pair, tf, side)
    ts = last_alert_at.get(key)
    if ts is None:
        return True
    return (now_utc - ts) >= timedelta(minutes=ALERT_COOLDOWN_MIN)

def mark_alert(pair: str, tf: str, side: str, when_utc: datetime) -> None:
    last_alert_at[(pair, tf, side)] = when_utc

def main():
    print("=== FX Levels Bot started ===")
    chat_ids = load_chat_ids()
    chat_ids = fetch_new_chat_ids(chat_ids)
    if chat_ids:
        print(f"Loaded chat_ids: {chat_ids}")
    else:
        print("Нет chat_id. Отправь /start своему боту в Telegram — я подхвачу chat_id автоматически.")

    local_tz = pytz.timezone(TZ_NAME)

    while True:
        loop_start_utc = datetime.now(timezone.utc)
        chat_ids = fetch_new_chat_ids(chat_ids)
        save_chat_ids(chat_ids)

        if not chat_ids:
            time.sleep(CHECK_INTERVAL_SEC)
            continue

        for pair in PAIRS:
            symbol = YF_SYMBOLS.get(pair)
            if not symbol:
                print(f"[WARN] Нет Yahoo-символа для {pair}")
                continue

            try:
                df = fetch_history(symbol, lookback_minutes=max(WINDOWS_MINUTES.values()))
                if df.empty:
                    print(f"[DATA] Пусто для {pair}/{symbol}")
                    continue

                current_price = float(df["Close"].iloc[-1])

                for tf, minutes in WINDOWS_MINUTES.items():
                    lv, hv = compute_levels(df, minutes)
                    if lv is None or hv is None:
                        continue

                    dist_to_min = pct_distance(current_price, lv)
                    if dist_to_min <= DISTANCE_PCT and can_alert(pair, tf, "MIN", loop_start_utc):
                        mark_alert(pair, tf, "MIN", loop_start_utc)
                        local_time_str = loop_start_utc.astimezone(local_tz).strftime("%Y-%m-%d %H:%M:%S")
                        text = (
                            f"⚠️ <b>{pair}</b>\n"
                            f"ТФ: <b>{tf}</b>\n"
                            f"Цена: <b>{current_price:.5f}</b>\n"
                            f"Близко к <b>MIN</b> {tf}: <b>{lv:.5f}</b>\n"
                            f"Дистанция: <b>{dist_to_min:.3f}%</b>\n"
                            f"⏰ {local_time_str} ({TZ_NAME})"
                        )
                        for cid in chat_ids:
                            send_message(cid, text)

                    dist_to_max = pct_distance(current_price, hv)
                    if dist_to_max <= DISTANCE_PCT and can_alert(pair, tf, "MAX", loop_start_utc):
                        mark_alert(pair, tf, "MAX", loop_start_utc)
                        local_time_str = loop_start_utc.astimezone(local_tz).strftime("%Y-%m-%d %H:%M:%S")
                        text = (
                            f"⚠️ <b>{pair}</b>\n"
                            f"ТФ: <b>{tf}</b>\n"
                            f"Цена: <b>{current_price:.5f}</b>\n"
                            f"Близко к <b>MAX</b> {tf}: <b>{hv:.5f}</b>\n"
                            f"Дистанция: <b>{dist_to_max:.3f}%</b>\n"
                            f"⏰ {local_time_str} ({TZ_NAME})"
                        )
                        for cid in chat_ids:
                            send_message(cid, text)

            except Exception as e:
                print(f"[ERROR] {pair}/{symbol}: {e}")

        time.sleep(CHECK_INTERVAL_SEC)

if __name__ == "__main__":
    main()
