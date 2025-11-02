import asyncio
import os
import time
from datetime import datetime, timezone

import ccxt
import pandas as pd
from telegram import Bot

# --------- параметры из окружения ---------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # число или @username
EXCHANGE = os.getenv("EXCHANGE", "binance")
SYMBOL = os.getenv("SYMBOL", "BTC/USDT")
THRESHOLD = float(os.getenv("THRESHOLD", "0.001"))  # 0.001 = 0.1%
POLL_SEC = int(os.getenv("POLL_SEC", "30"))
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", "900"))
LOOKBACK_5M = 288  # 24ч * 60 / 5
# ------------------------------------------

bot = Bot(TELEGRAM_TOKEN)
last_signal_at = {}  # (tf, type, price) -> ts

def now_utc():
    return datetime.now(timezone.utc)

def ensure_env():
    miss = []
    if not TELEGRAM_TOKEN: miss.append("TELEGRAM_TOKEN")
    if not TELEGRAM_CHAT_ID: miss.append("TELEGRAM_CHAT_ID")
    if miss:
        raise RuntimeError("Заполните переменные окружения: " + ", ".join(miss))

def get_exchange():
    ex = getattr(ccxt, EXCHANGE)()
    ex.enableRateLimit = True
    return ex

async def fetch_ohlcv(ex, timeframe: str, limit: int):
    data = await asyncio.to_thread(ex.fetch_ohlcv, SYMBOL, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(data, columns=["ts", "open", "high", "low", "close", "volume"])
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df

def levels_from_5m(df_5m: pd.DataFrame):
    df = df_5m.set_index("dt").sort_index()
    end = df.index.max()
    r1  = df.loc[end - pd.Timedelta(hours=1) : end]
    r12 = df.loc[end - pd.Timedelta(hours=12): end]
    r24 = df.loc[end - pd.Timedelta(hours=24): end]
    def hl(r): return float(r["high"].max()), float(r["low"].min())
    h1,l1 = hl(r1); h12,l12 = hl(r12); h24,l24 = hl(r24)
    return {"1h":{"high":h1,"low":l1}, "12h":{"high":h12,"low":l12}, "24h":{"high":h24,"low":l24}}

def should_alert(key): 
    ts = last_signal_at.get(key); 
    return ts is None or (time.time()-ts) >= COOLDOWN_SEC

def mark_alert(key): 
    last_signal_at[key] = time.time()

async def send_signal(tf, level_type, level_price, price, distance):
    txt = (
        f"⚠️ Подход к уровню {tf} {level_type.upper()}\n"
        f"{SYMBOL}\nЦена: {price:.6f}\nУровень: {level_price:.6f}\n"
        f"Отклонение: {distance*100:.3f}%\n{now_utc():%Y-%m-%d %H:%M:%S} UTC"
    )
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=txt)

async def main_loop():
    ensure_env()
    ex = get_exchange()
    while True:
        try:
            df5 = await fetch_ohlcv(ex, "5m", LOOKBACK_5M)
            last_close = float(df5["close"].iloc[-1])
            last_high  = float(df5["high"].iloc[-1])
            last_low   = float(df5["low"].iloc[-1])

            lvls = levels_from_5m(df5)

            for tf, pair in lvls.items():
                for lt, lp in pair.items():  # lt = high/low
                    touched = (lt=="high" and last_high>=lp) or (lt=="low" and last_low<=lp)
                    dist = abs(last_close-lp)/lp
                    close_enough = dist <= THRESHOLD
                    if touched or close_enough:
                        key = (tf, lt, round(lp,8))
                        if should_alert(key):
                            mark_alert(key)
                            await send_signal(tf, lt, lp, last_close, dist)
        except Exception as e:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"Ошибка: {e}")
        await asyncio.sleep(POLL_SEC)

if __name__ == "__main__":
    asyncio.run(main_loop())
