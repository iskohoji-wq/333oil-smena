"""
Хранилище на JSON-файлах — как в 333 OIL.

ВАЖНО: на Railway без подключённого Volume файловая система эфемерна —
данные пропадут при каждом редеплое. Пока Volume не настроен, эти файлы
нельзя считать единственной копией отчётов.

Архитектура — под несколько станций сразу (сейчас реально работает
station_1, остальные 4 добавляются владельцем через Mini App, когда
будут готовы их калибровочные данные).
"""
import json
import os
import threading
from datetime import datetime, timezone, timedelta

from config import DATA_DIR

_lock = threading.Lock()

os.makedirs(DATA_DIR, exist_ok=True)

OPERATORS_FILE = os.path.join(DATA_DIR, "operators.json")
PENDING_FILE = os.path.join(DATA_DIR, "pending.json")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.json")
STATIONS_FILE = os.path.join(DATA_DIR, "stations.json")
LANG_FILE = os.path.join(DATA_DIR, "lang_prefs.json")

ARCHIVE_DAYS = 180  # 6 месяцев
DEFAULT_STATION_ID = "station_1"


def _read(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def _write(path, data):
    with _lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- Язык ----------

def get_lang(telegram_id: int, default: str = "ru") -> str:
    prefs = _read(LANG_FILE, {})
    return prefs.get(str(telegram_id), default)


def set_lang(telegram_id: int, lang: str):
    prefs = _read(LANG_FILE, {})
    prefs[str(telegram_id)] = lang
    _write(LANG_FILE, prefs)
    ops = get_operators()
    if str(telegram_id) in ops:
        ops[str(telegram_id)]["lang"] = lang
        _write(OPERATORS_FILE, ops)


# ---------- Операторы ----------

def get_operators():
    return _read(OPERATORS_FILE, {})


def add_operator(telegram_id: int, name: str, phone: str, lang: str = "ru", station_id: str = DEFAULT_STATION_ID):
    ops = get_operators()
    ops[str(telegram_id)] = {
        "name": name,
        "phone": phone,
        "lang": lang,
        "station_id": station_id,
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    _write(OPERATORS_FILE, ops)


def is_operator(telegram_id: int) -> bool:
    return str(telegram_id) in get_operators()


def get_operator_station(telegram_id: int) -> str:
    ops = get_operators()
    return ops.get(str(telegram_id), {}).get("station_id", DEFAULT_STATION_ID)


# ---------- Заявки на регистрацию ----------

def get_pending():
    return _read(PENDING_FILE, {})


def add_pending(telegram_id: int, name: str, phone: str):
    pending = get_pending()
    pending[str(telegram_id)] = {
        "name": name,
        "phone": phone,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    _write(PENDING_FILE, pending)


def remove_pending(telegram_id: int):
    pending = get_pending()
    pending.pop(str(telegram_id), None)
    _write(PENDING_FILE, pending)


def is_pending(telegram_id: int) -> bool:
    return str(telegram_id) in get_pending()


# ---------- Станции ----------

def _default_station(name: str) -> dict:
    return {
        "name": name,
        "tank_names": {},
        "counter_tags": {"A": "А", "B": "Б", "V": "В", "G": "Г"},
        "counter_values": {"A": 0, "B": 0, "V": 0, "G": 0},
        "counters_initialized": False,   # как только владелец задаст стартовые числа — станет True навсегда
        "last_tank_liters": {"1": None, "2": None, "3": None, "4": None},
        "prices": {"АИ-92": 7600, "АИ-95": 8900, "АИ-98": 10200},
    }


def get_stations() -> dict:
    stations = _read(STATIONS_FILE, None)
    if stations is None:
        stations = {DEFAULT_STATION_ID: _default_station("АЗС №1")}
        _write(STATIONS_FILE, stations)
    return stations


def get_station(station_id: str = DEFAULT_STATION_ID) -> dict:
    stations = get_stations()
    if station_id not in stations:
        stations[station_id] = _default_station(station_id)
        _write(STATIONS_FILE, stations)
    return stations[station_id]


def create_station(station_id: str, name: str):
    stations = get_stations()
    if station_id not in stations:
        stations[station_id] = _default_station(name)
        _write(STATIONS_FILE, stations)
    return stations[station_id]


def rename_station(station_id: str, name: str):
    stations = get_stations()
    if station_id not in stations:
        stations[station_id] = _default_station(name)
    else:
        stations[station_id]["name"] = name
    _write(STATIONS_FILE, stations)
    return stations[station_id]


def update_station_settings(station_id: str, patch: dict):
    """Для названий котлов/тегов/цен/имени станции. НЕ трогает counter_values —
    для этого есть отдельные функции с блокировкой ниже."""
    patch = {k: v for k, v in patch.items() if k not in ("counter_values", "counters_initialized")}
    stations = get_stations()
    cfg = stations.get(station_id) or _default_station(station_id)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(value)
        else:
            cfg[key] = value
    stations[station_id] = cfg
    _write(STATIONS_FILE, stations)
    return cfg


def set_initial_counters(station_id: str, values: dict) -> bool:
    """Владелец задаёт стартовые показания А/Б/В/Г в первый рабочий день.
    Разрешено ТОЛЬКО один раз — дальше заблокировано навсегда.
    Возвращает True если применилось, False если уже было заблокировано."""
    stations = get_stations()
    cfg = stations.get(station_id) or _default_station(station_id)
    if cfg.get("counters_initialized"):
        return False
    cfg["counter_values"] = {**cfg["counter_values"], **values}
    cfg["counters_initialized"] = True
    stations[station_id] = cfg
    _write(STATIONS_FILE, stations)
    return True


def apply_shift_end_counters(station_id: str, values: dict):
    """Системное обновление показаний после закрытия смены — не владелец,
    к блокировке не имеет отношения, разрешено всегда."""
    stations = get_stations()
    cfg = stations.get(station_id) or _default_station(station_id)
    cfg["counter_values"] = {**cfg["counter_values"], **values}
    stations[station_id] = cfg
    _write(STATIONS_FILE, stations)


# ---------- Отчёты по сменам ----------

def _cleanup_old_shifts(shifts: list) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(days=ARCHIVE_DAYS)
    kept = []
    for s in shifts:
        try:
            ts = datetime.fromisoformat(s["submitted_at"])
        except (KeyError, ValueError):
            kept.append(s)
            continue
        if ts >= cutoff:
            kept.append(s)
    return kept


def get_shifts(station_id: str = None, date: str = None) -> list:
    """date — строка 'YYYY-MM-DD', фильтрует по дате отправки отчёта."""
    shifts = _read(SHIFTS_FILE, [])
    if station_id:
        shifts = [s for s in shifts if s.get("station_id") == station_id]
    if date:
        shifts = [s for s in shifts if s.get("submitted_at", "").startswith(date)]
    return shifts


def add_shift(shift: dict):
    shifts = _read(SHIFTS_FILE, [])
    shift["submitted_at"] = datetime.now(timezone.utc).isoformat()
    shifts.append(shift)
    shifts = _cleanup_old_shifts(shifts)
    _write(SHIFTS_FILE, shifts)
    return shift
