"""
Простое хранилище на JSON-файлах — как в 333 OIL (orders.json).

ВАЖНО: на Railway без подключённого Volume файловая система эфемерна —
данные пропадут при каждом редеплое. Это тот же нюанс, что уже встречался
в 333 OIL. Пока Volume не настроен, стоит считать эти файлы временными
и не полагаться на них как единственную копию важных отчётов.
"""
import json
import os
import threading
from datetime import datetime, timezone

from config import DATA_DIR

_lock = threading.Lock()

os.makedirs(DATA_DIR, exist_ok=True)

OPERATORS_FILE = os.path.join(DATA_DIR, "operators.json")
PENDING_FILE = os.path.join(DATA_DIR, "pending.json")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.json")
STATION_FILE = os.path.join(DATA_DIR, "station_config.json")
LANG_FILE = os.path.join(DATA_DIR, "lang_prefs.json")


def get_lang(telegram_id, default="ru"):
    prefs = _read(LANG_FILE, {})
    return prefs.get(str(telegram_id), default)


def set_lang(telegram_id, lang):
    prefs = _read(LANG_FILE, {})
    prefs[str(telegram_id)] = lang
    _write(LANG_FILE, prefs)
    ops = get_operators()
    if str(telegram_id) in ops:
        ops[str(telegram_id)]["lang"] = lang
        _write(OPERATORS_FILE, ops)


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


def get_operators():
    return _read(OPERATORS_FILE, {})


def add_operator(telegram_id, name, phone, lang="ru"):
    ops = get_operators()
    ops[str(telegram_id)] = {
        "name": name,
        "phone": phone,
        "lang": lang,
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    _write(OPERATORS_FILE, ops)


def is_operator(telegram_id):
    return str(telegram_id) in get_operators()


def get_operator_lang(telegram_id, default="ru"):
    return get_lang(telegram_id, default)


def set_operator_lang(telegram_id, lang):
    ops = get_operators()
    if str(telegram_id) in ops:
        ops[str(telegram_id)]["lang"] = lang
        _write(OPERATORS_FILE, ops)


def get_pending():
    return _read(PENDING_FILE, {})


def add_pending(telegram_id, name, phone):
    pending = get_pending()
    pending[str(telegram_id)] = {
        "name": name,
        "phone": phone,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    _write(PENDING_FILE, pending)


def remove_pending(telegram_id):
    pending = get_pending()
    pending.pop(str(telegram_id), None)
    _write(PENDING_FILE, pending)


def is_pending(telegram_id):
    return str(telegram_id) in get_pending()


DEFAULT_STATION_CONFIG = {
    "tank_names": {},
    "counter_tags": {"A": "А", "B": "Б", "V": "В", "G": "Г"},
    "counter_values": {"A": 0, "B": 0, "V": 0, "G": 0},
    "last_tank_liters": {"1": None, "2": None, "3": None, "4": None},
    "prices": {"АИ-92": 7600, "АИ-95": 8900, "АИ-98": 10200},
}


def get_station_config():
    cfg = _read(STATION_FILE, None)
    if cfg is None:
        cfg = DEFAULT_STATION_CONFIG.copy()
        _write(STATION_FILE, cfg)
    return cfg


def update_station_config(patch):
    cfg = get_station_config
