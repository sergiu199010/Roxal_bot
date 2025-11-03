# main.py
import os
import time
import math
import json
import threading
from collections import deque, defaultdict
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import telebot

# ========= НАСТРОЙКИ =========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Интервал проверки (сек)
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))
# Близость к уровню (в % от цены). 0.08 = 0.08%
NEAR_THRESH_PCT = float(os.getenv("NEAR_THRESH_PCT", "0.08"))
# Кулдаун между сигналами по одной паре (сек)
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", "300"))
# Смещение часового пояса для показа времени
TZ_OFFSET = os.getenv("TZ_OFFSET", "+01:00")

# Список пар как на Pocket Option
PAIRS = [
    "EUR/USD","GBP/AUD","GBP/CHF","GBP/USD","USD/CHF","USD/JPY","GBP/CAD",
    "AUD/CAD","AUD/USD","USD/CAD","GBP/JPY","EUR/JPY","AUD/CHF","AUD/JPY",
    "CAD/CHF","CAD/JPY","CHF/JPY","EUR/AUD","EUR/CAD","EUR/CHF","EUR/GBP"
]

# Окна уровней (в минутах)
WINDOWS_MINUTES = {
    "30m": 30,
    "1h": 60,
    "3h": 180,
    "6h": 360,
    "12h": 720,
}

# Параметры Telegram-бота
if not TELEGRAM_TOKEN or not CHAT_ID:
    raise SystemExit("❗️Не заданы TELEGRAM_TOKEN или TELEGRAM_CHAT_ID в переменных окружения.")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")

# ========= ХРАНИЛКА ДАННЫХ =========
# История цен по парам: за последние 12 часов
price_history = defaultdict(lambda: deque())
# Последнее состояние сигнала для анти-спама
last_alert_state = {}
last_alert_time = {}

# ========= ВСПОМОГАТЕЛЬНОЕ =========
def parse_tz_offset(offset_str: str) -> timezone:
    try:
        sign = 1 if offset_str.startswith("+") else -1
        hh, mm = offset_str[1:].split(":")
        return timezone(sign * timedelta(hours=int(hh), minutes=int(mm)))
    except Exception:
        # по умолчанию UTC+1
        return timezone(timedelta(hours=1))

LOCAL_TZ = parse_tz_offset(TZ_OFFSET)

def now_local() -> datetime:
    return datetime.now(tz=LOCAL_TZ)

def fmt_time(dt: datetime) -> str:
    return dt.strftime("%H:%M:%S")

def pair_to_base_quote(pair: str):
    base, quote = pair.split("/")
    return base, quote

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "RoxalBot/1.0"})

def get_rate_exchangerate_host(pair: str) -> float | None:
    """Нератлимитный источник: exchangerate.host (convert). Возвращает float или None."""
    base, quote = pair_to_base_quote(pair)
    url = f"https://api.exchangerate.host/convert?from={base}&to={quote}"
    try:
        r = SESSION.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            # ожидаем ключ result
            rate = data.get("result")
            if isinstance(rate, (int, float)) and rate > 0:
                return float(rate)
    except Exception as e:
        print(f"⚠️ Ошибка запроса {pair}: {e}")
    return None

def fetch_all_prices(pairs: list[str]) -> dict[str, float | None]:
    out = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(get_rate_exchangerate_host, p): p for p in pairs}
        for fu in as_completed(futures):
            p = futures[fu]
            try:
                out[p] = fu.result()
            except Exception as e:
                print(f"⚠️ Ошибка потока {p}: {e}")
                out[p] = None
    return out

def update_history(prices: dict[str, float | None]):
    cutoff = datetime.utcnow() - timedelta(minutes=max(WINDOWS_MINUTES.values()))
    for pair, price in prices.items():
        if price is None:
            continue
        q = price_history[pair]
        # записываем как (UTC-время, цена)
        q.append((datetime.utcnow(), price))
        # чистим старое
        while q and q[0][0] < cutoff:
            q.popleft()

def window_min_max(pair: str, minutes_back: int) -> tuple[float | None, float | None]:
    """Мин/Макс по истории за окно в минутах."""
    since = datetime.utcnow() - timedelta(minutes=minutes_back)
    q = price_history[pair]
    vals = [v for t, v in q if t >= since]
    if not vals:
        return None, None
    return (min(vals), max(vals))

def consecutive_moves(pair: str, steps: int = 4) -> str | None:
    """Грубая оценка направления: 4+ подряд аптиков/даунтиков по 30-сек отсчётам."""
    q = price_history[pair]
    if len(q) < steps + 1:
        return None
    # берём последние steps+1 точек
    pts = list(q)[- (steps + 1):]
    ups = 0
    downs = 0
    for i in range(1, len(pts)):
        if pts[i][1] > pts[i-1][1]:
            ups += 1
        elif pts[i][1] < pts[i-1][1]:
            downs += 1
        else:
            return None
    if ups >= steps:
        return "4+ зелёных подряд"
    if downs >= steps:
        return "4+ красных подряд"
    return None

def pct_distance(price: float, level: float) -> float:
    return abs(price - level) / price * 100.0

def build_signal(pair: str, price: float) -> dict:
    """Собираем информацию по окнам, если близко к уровням."""
    near_max = []
    near_min = []
    for tag, mins in WINDOWS_MINUTES.items():
        mn, mx = window_min_max(pair, mins)
        if mn is None or mx is None:
            continue
        # близость к максимуму
        if pct_distance(price, mx) <= NEAR_THRESH_PCT:
            near_max.append((tag, mx, pct_distance(price, mx), "↓" if price <= mx else "↑"))
        # близость к минимуму
        if pct_distance(price, mn) <= NEAR_THRESH_PCT:
            near_min.append((tag, mn, pct_distance(price, mn), "↑" if price >= mn else "↓"))

    if not near_max and not near_min:
        return {}

    trend_note = consecutive_moves(pair, steps=4)

    info = {
        "pair": pair,
        "price": price,
        "when": now_local(),
        "near_max": sorted(near_max, key=lambda x: WINDOWS_MINUTES[x[0]]),
        "near_min": sorted(near_min, key=lambda x: WINDOWS_MINUTES[x[0]]),
        "trend": trend_note
    }
    return info

def format_signal_text(sig: dict) -> str:
    pair = sig["pair"]
    price = sig["price"]
    tm = sig["when"]
    lines = []
    lines.append("🔔 <b>СИГНАЛ</b>")
    lines.append(f"<b>{pair}</b> | {fmt_time(tm)} (UTC{TZ_OFFSET})")
    lines.append(f"Цена: <b>{price:.5f}</b>")

    if sig["near_max"]:
        lines.append("Близко к <b>МАКСИМУМАМ</b>:")
        for tag, lvl, dist, arrow in sig["near_max"]:
            lines.append(f"• {tag}: max {lvl:.5f} ({dist:.3f}% {arrow})")
    if sig["near_min"]:
        lines.append("Близко к <b>МИНИМУМАМ</b>:")
        for tag, lvl, dist, arrow in sig["near_min"]:
            lines.append(f"• {tag}: min {lvl:.5f} ({dist:.3f}% {arrow})")

    if sig["trend"]:
        lines.append(f"Условие свечей: <b>{sig['trend']}</b>")

    lines.append("\n— Roxal_bot")
    return "\n".join(lines)

def state_signature(sig: dict) -> str:
    """Хэш состояния для анти-спама — какие окна сработали и с какой стороны."""
    parts = []
    for tag, *_ in sig.get("near_max", []):
        parts.append(f"MAX:{tag}")
    for tag, *_ in sig.get("near_min", []):
        parts.append(f"MIN:{tag}")
    if sig.get("trend"):
        parts.append(f"TREND:{sig['trend']}")
    return "|".join(parts) or "EMPTY"

def send_signal(sig: dict):
    text = format_signal_text(sig)
    try:
        # Обычное уведомление (звучит «средний» системный звук Телеграма)
        bot.send_message(CHAT_ID, text, disable_notification=False)
    except Exception as e:
        print(f"⚠️ Ошибка отправки в Telegram: {e}")

def checker_loop():
    print("🚀 Бот запущен. Ожидает /start в Telegram.")
    # Пишем в канал, что бот активен
    try:
        bot.send_message(CHAT_ID, f"✅ Бот активен. Проверяю уровни каждые {CHECK_INTERVAL} сек.")
    except Exception:
        pass

    while True:
        try:
            prices = fetch_all_prices(PAIRS)
            update_history(prices)

            for pair, price in prices.items():
                if price is None:
                    continue

                sig = build_signal(pair, price)
                if not sig:
                    continue

                stamp = state_signature(sig)
                now_ts = time.time()
                last_ts = last_alert_time.get(pair, 0)
                last_state = last_alert_state.get(pair, "")

                # анти-спам: кулдаун + изменения в состоянии
                if (now_ts - last_ts) >= COOLDOWN_SEC and stamp != last_state:
                    send_signal(sig)
                    last_alert_time[pair] = now_ts
                    last_alert_state[pair] = stamp

        except Exception as e:
            print(f"⚠️ Ошибка основного цикла: {e}")
        time.sleep(CHECK_INTERVAL)

# ========= Обработчик /start =========
@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        f"✅ Бот запущен. Проверяю уровни каждые {CHECK_INTERVAL} секунд.\n"
        f"Порог близости к уровню: {NEAR_THRESH_PCT:.3f}%.\n"
        f"Время в сообщениях: UTC{TZ_OFFSET}."
    )

def run():
    # отдельный поток для проверки уровней
    t = threading.Thread(target=checker_loop, daemon=True)
    t.start()
    # безопасный polling с пропуском старых апдейтов
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)

if __name__ == "__main__":
    run()
