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


# ---------- Операторы ----------

def get_operators():
    """{ telegram_id(str): {name, phone, lang, approved_at} }"""
    return _read(OPERATORS_FILE, {})


def add_operator(telegram_id: int, name: str, phone: str, lang: str = "ru"):
    ops = get_operators()
    ops[str(telegram_id)] = {
        "name": name,
        "phone": phone,
        "lang": lang,
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    _write(OPERATORS_FILE, ops)


def is_operator(telegram_id: int) -> bool:
    return str(telegram_id) in get_operators()


def get_operator_lang(telegram_id: int, default="ru") -> str:
    ops = get_operators()
    return ops.get(str(telegram_id), {}).get("lang", default)


def set_operator_lang(telegram_id: int, lang: str):
    ops = get_operators()
    if str(telegram_id) in ops:
        ops[str(telegram_id)]["lang"] = lang
        _write(OPERATORS_FILE, ops)


# ---------- Заявки на регистрацию (ожидают владельца) ----------

def get_pending():
    """{ telegram_id(str): {name, phone, requested_at} }"""
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


# ---------- Настройки станции: названия котлов, цены, показания счётчиков ----------

DEFAULT_STATION_CONFIG = {
    "tank_names": {},       # {"1": "Котёл 1 · АИ-92", ...} — override, иначе берётся дефолт из calibration.py
    "counter_tags": {"A": "А", "B": "Б", "V": "В", "G": "Г"},
    "counter_values": {"A": 0, "B": 0, "V": 0, "G": 0},   # текущее показание "было" на конец последней смены
    "last_tank_liters": {"1": None, "2": None, "3": None, "4": None},  # калибровка на конец прошлой смены
    "prices": {"АИ-92": 7600, "АИ-95": 8900, "АИ-98": 10200},
}


def get_station_config():
    cfg = _read(STATION_FILE, None)
    if cfg is None:
        cfg = DEFAULT_STATION_CONFIG.copy()
        _write(STATION_FILE, cfg)
    return cfg


def update_station_config(patch: dict):
    cfg = get_station_config()
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(value)
        else:
            cfg[key] = value
    _write(STATION_FILE, cfg)
    return cfg


# ---------- Отчёты по сменам ----------

def get_shifts():
    return _read(SHIFTS_FILE, [])


def add_shift(shift: dict):
    shifts = get_shifts()
    shift["submitted_at"] = datetime.now(timezone.utc).isoformat()
    shifts.append(shift)
    _write(SHIFTS_FILE, shifts)
    return shift
