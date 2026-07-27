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
        "counters_initialized": False,
        "last_tank_liters": {"1": None, "2": None, "3": None, "4": None},
        "prices": {"АИ-92": 7600, "АИ-95": 8900, "АИ-98": 10200},
    }


def get_stations() -> dict:
    stations = _read(STATIONS_FIL
