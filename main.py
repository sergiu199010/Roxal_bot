# main.py
# RoxaL Trade — уровни 30м/1ч/3ч/6ч/12ч, проверка каждые 30 сек,
# источник котировок: exchangerate.host (без ключей)

import os
import time
import threading
import requests
from datetime import datetime, timedelta, timezone
import telebot

# ---------- Настройки ----------
CHECK_INTERVAL_SEC = 30                   # опрос каждые 30 секунд
NEAR_THRESHOLD_PCT = 0.08                 # порог близости к уровню в %
TIMEFRAMES = [
    ("30m", timedelta(minutes=30)),
    ("1h",  timedelta(hours=1)),
    ("3h",  timedelta(hours=3)),
    ("6h",  timedelta(hours=6)),
    ("12h", timedelta(hours=12)),
]

# пары (все основные с PocketOption)
PAIRS = [
    "EUR/USD","GBP/AUD","GBP/CHF","GBP/USD","USD/CHF","USD/JPY","GBP/CAD",
    "AUD/CAD","AUD/USD","USD/CAD","GBP/JPY","EUR/JPY","AUD/CHF","AUD/JPY",
    "CAD/CHF","CAD/JPY","CHF/JPY","EUR/AUD","EUR/CAD","EUR/CHF","EUR/GBP"
]

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()  # можно указать канал/чат в переменных Railway
if not TELEGRAM_TOKEN:
    raise SystemExit("TELEGRAM_TOKEN не задан")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")

# ---------- Хранилище котировок и алертов ----------
# history[pair] = list[(ts, price)], храним за последние 13 часов
history = {p: [] for p in PAIRS}

# защита от спама: (pair, tf_name, 'max'/'min') -> last_ts
last_alert = {}

HISTORY_KEEP = max(tf for _, tf in TIMEFRAMES) + timedelta(hours=1)

UTC_TZ = timezone.utc

# ---------- Утилиты времени ----------
def now_utc():
    return datetime.now(tz=UTC_TZ)

def format_ts_local(ts: datetime, utc_offset_hours: int = 1):
    # Печатаем время с твоим часовым поясом (UTC+01:00 как в примерах)
    local = ts + timedelta(hours=utc_offset_hours)
    return local.strftime("%H:%M:%S")

# ---------- Котировки с exchangerate.host ----------
# Для экономии запросов делаем батчи по базовым валютам
def fetch_prices_batch():
    """
    Возвращает словарь {'EUR/USD': 1.0743, ...} или None при ошибке.
    """
    bases = set(p.split('/')[0] for p in PAIRS)
    wants = {}
    for base in bases:
        symbols = []
        for pair in PAIRS:
            b, q = pair.split('/')
            if b == base:
                symbols.append(q)
        if not symbols:
            continue
        url = f"https://api.exchangerate.host/latest"
        params = {"base": base, "symbols": ",".join(symbols)}
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            rates = data.get("rates", {})
            for sym, val in rates.items():
                wants[f"{base}/{sym}"] = float(val)
        except Exception as e:
            print(f"⚠️ Ошибка запроса {base}: {e}")
            return None
        time.sleep(0.05)  # маленькая пауза, чтобы не долбить
    return wants

# ---------- Обновление истории ----------
def push_price(pair: str, price: float, ts: datetime):
    arr = history[pair]
    arr.append((ts, price))
    # чистим старое
    cutoff = ts - HISTORY_KEEP
    while arr and arr[0][0] < cutoff:
        arr.pop(0)

# ---------- Свечи M5 для streak (серии) ----------
def get_m5_closes(pair: str, ts: datetime, bars: int = 5):
    """
    Собираем квази-свечи М5 из последних цен (берем последний тик внутри каждого 5-минутного ведра).
    Возвращает список клоузов от старых к новым, длиной до bars.
    """
    bucket = {}
    for t, price in history[pair]:
        # округляем вниз к 5-минутке
        minute = (t.minute // 5) * 5
        t5 = t.replace(minute=minute, second=0, microsecond=0)
        bucket[t5] = price  # берем последний попавший в ведро

    keys = sorted([k for k in bucket.keys() if k <= ts])[-bars:]
    return [bucket[k] for k in keys]

def four_same_streak(pair: str, ts: datetime):
    """
    Есть ли подряд >=4 зеленых или >=4 красных М5 свечи (по клоузам)?
    Возвращает ('green'|'red'|None)
    """
    closes = get_m5_closes(pair, ts, bars=5)
    if len(closes) < 5:
        return None
    # смотрим последние 4 изменения
    d = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    last4 = d[-4:]
    if all(x > 0 for x in last4):
        return "green"
    if all(x < 0 for x in last4):
        return "red"
    return None

# ---------- Поиск уровней ----------
def compute_levels(pair: str, ts: datetime):
    """
    Для каждой ТФ считаем min/max за окно.
    Возвращает dict: { '30m': (min,max), ... } где min/max = None, если данных мало.
    """
    arr = history[pair]
    res = {}
    for name, delta in TIMEFRAMES:
        since = ts - delta
        window = [p for (t, p) in arr if t >= since]
        if len(window) < 3:
            res[name] = (None, None)
        else:
            res[name] = (min(window), max(window))
    return res

# ---------- Сигнал ----------
def maybe_signal(pair: str, price: float, ts: datetime):
    levels = compute_levels(pair, ts)
    streak = four_same_streak(pair, ts)
    signals_out = []

    for tf_name, _ in TIMEFRAMES:
        min_lvl, max_lvl = levels[tf_name]

        if min_lvl is None or max_lvl is None:
            continue

        dist_min = abs(price - min_lvl) / price * 100.0
        dist_max = abs(price - max_lvl) / price * 100.0

        # проверяем минимум
        if dist_min <= NEAR_THRESHOLD_PCT:
            key = (pair, tf_name, "min")
            if ts.timestamp() - last_alert.get(key, 0) >= 60:  # не чаще 1 раза в минуту по одному уровню
                last_alert[key] = ts.timestamp()
                signals_out.append(("min", tf_name, min_lvl, dist_min))

        # проверяем максимум
        if dist_max <= NEAR_THRESHOLD_PCT:
            key = (pair, tf_name, "max")
            if ts.timestamp() - last_alert.get(key, 0) >= 60:
                last_alert[key] = ts.timestamp()
                signals_out.append(("max", tf_name, max_lvl, dist_max))

    if not signals_out:
        return

    # Собираем единое сообщение
    lines = []
    header = f"🔔 <b>{pair}</b> — цена близка к уровню"
    lines.append(header)
    lines.append(f"Цена: <b>{price:.6f}</b> (UTC {format_ts_local(ts, utc_offset_hours=1)})")

    for typ, tf_name, lvl, dist in sorted(signals_out, key=lambda x: x[1]):
        what = "минимуму" if typ == "min" else "максимуму"
        lines.append(f"• <b>{tf_name}</b>: {what} — уровень <b>{lvl:.6f}</b> | отклонение <b>{dist:.3f}%</b>")

    if streak == "green":
        lines.append("↗️ Серия: ≥4 <b>зелёных</b> М5 подряд")
    elif streak == "red":
        lines.append("↘️ Серия: ≥4 <b>красных</b> М5 подряд")

    text = "\n".join(lines)

    # Обычное (не-тихое) уведомление = «средний» звук Telegram
    try:
        if TELEGRAM_CHAT_ID:
            bot.send_message(TELEGRAM_CHAT_ID, text, disable_notification=False)
        else:
            # если чат не задан переменной — пошлём в последний /start
            # (перепишется в обработчике /start)
            pass
    except Exception as e:
        print(f"⚠️ Ошибка отправки сигнала {pair}: {e}")

# ---------- Основной цикл ----------
def worker_loop():
    print("🚀 Бот запущен. Ожидаю /start в Telegram.")
    while True:
        try:
            prices = fetch_prices_batch()
            ts = now_utc()
            if prices is None:
                time.sleep(CHECK_INTERVAL_SEC)
                continue

            # записываем историю и проверяем сигналы
            for pair, px in prices.items():
                push_price(pair, px, ts)
                maybe_signal(pair, px, ts)

        except Exception as e:
            print(f"⚠️ Ошибка цикла: {e}")
        time.sleep(CHECK_INTERVAL_SEC)

# ---------- Команды бота ----------
last_start_chat = None

@bot.message_handler(commands=['start'])
def start_cmd(message):
    global last_start_chat
    last_start_chat = message.chat.id
    msg = (
        "✅ Бот запущен. Проверяю уровни каждые <b>30 секунд</b>.\n"
        f"Порог близости к уровню: <b>{NEAR_THRESHOLD_PCT:.3f}%</b>.\n"
        "ТФ уровней: <b>30м, 1ч, 3ч, 6ч, 12ч</b>.\n"
        "Время в сообщениях: <b>UTC+01:00</b>.\n"
        "Звук уведомления: <b>обычный</b> (не тихий).\n"
        "Источник цен: <b>exchangerate.host</b>."
    )
    bot.send_message(message.chat.id, msg, disable_notification=False)

@bot.message_handler(commands=['status'])
def status_cmd(message):
    ts = now_utc()
    filled = sum(1 for p in PAIRS if len(history[p]) > 0)
    bot.send_message(
        message.chat.id,
        f"ℹ️ Статус на {format_ts_local(ts, 1)}\n"
        f"Пары с данными: <b>{filled}/{len(PAIRS)}</b>\n"
        f"Интервал: <b>{CHECK_INTERVAL_SEC}s</b> | Порог: <b>{NEAR_THRESHOLD_PCT:.3f}%</b>",
        disable_notification=True
    )

# ---------- Запуск ----------
def run():
    # стартуем поток цен
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()

    # Long polling Telegram (skip старые)
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)

if __name__ == "__main__":
    run()
