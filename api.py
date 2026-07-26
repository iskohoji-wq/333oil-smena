"""
HTTP API для Mini App (оператор + владелец).

Все "тяжёлые" расчёты (литры по калибровке, продано по счётчикам, выручка,
расхождения) считаются ЗДЕСЬ, на сервере — Mini App присылает только сырые
цифры (см/мм, показания счётчиков), а не готовую сумму. Так оператор не может
случайно или намеренно исказить итог на своей стороне.
"""
from datetime import datetime, timezone

from aiohttp import web

import storage
from calibration import TANKS, COUNTER_TO_TANK, liters_from_dip, tank_name
from config import OWNER_IDS


def cors_middleware(allowed_origin: str = "*"):
    @web.middleware
    async def middleware(request, handler):
        if request.method == "OPTIONS":
            response = web.Response()
        else:
            response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = allowed_origin
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response
    return middleware


def _is_owner(tg_id) -> bool:
    try:
        return int(tg_id) in OWNER_IDS
    except (TypeError, ValueError):
        return False


async def get_config(request: web.Request):
    tg_id = request.query.get("tg_id")
    lang = storage.get_operator_lang(int(tg_id)) if tg_id and tg_id.isdigit() else "ru"

    if not tg_id or not (storage.is_operator(int(tg_id)) or _is_owner(tg_id)):
        return web.json_response({"error": "not_authorized"}, status=403)

    cfg = storage.get_station_config()
    tanks_out = []
    for tank_id, tank in TANKS.items():
        override = cfg["tank_names"].get(str(tank_id))
        tanks_out.append({
            "id": tank_id,
            "name": override or tank_name(tank_id, lang),
            "fuel": tank["fuel"],
            "max_cm": tank["max_cm"],
        })

    return web.json_response({
        "lang": lang,
        "tanks": tanks_out,
        "counter_tags": cfg["counter_tags"],
        "counter_values": cfg["counter_values"],
        "counter_to_tank": COUNTER_TO_TANK,
        "prices": cfg["prices"],
    })


async def submit_shift(request: web.Request):
    body = await request.json()
    tg_id = body.get("tg_id")

    if not tg_id or not storage.is_operator(int(tg_id)):
        return web.json_response({"error": "not_authorized"}, status=403)

    operators = storage.get_operators()
    operator_name = operators.get(str(tg_id), {}).get("name", "—")
    cfg = storage.get_station_config()

    # 1. Калибровка котлов -> литры
    tank_liters = {}
    for t in body.get("tanks", []):
        tank_id = int(t["tank_id"])
        cm = float(t.get("cm", 0))
        mm = float(t.get("mm", 0))
        tank_liters[tank_id] = liters_from_dip(tank_id, cm, mm)

    # 2. Счётчики -> продано литров, выручка, обновление "было" на след. смену
    prices = body.get("prices", cfg["prices"])
    counters_out = []
    total_liters = 0
    total_revenue = 0
    new_counter_values = dict(cfg["counter_values"])

    for c in body.get("counters", []):
        tag = c["tag"]
        end_reading = float(c["end_reading"])
        start_reading = float(cfg["counter_values"].get(tag, 0))
        sold = max(0, end_reading - start_reading)

        tank_id = COUNTER_TO_TANK.get(tag)
        fuel = TANKS[tank_id]["fuel"] if tank_id else None
        price = prices.get(fuel, 0) if fuel else 0
        revenue = sold * price

        total_liters += sold
        total_revenue += revenue
        new_counter_values[tag] = end_reading

        counters_out.append({
            "tag": tag, "tank_id": tank_id, "fuel": fuel,
            "sold_liters": sold, "price": price, "revenue": revenue,
        })

    # 3. Сверка расхождений: ожидаемый расход котла (по счётчику) vs факт по калибровке
    discrepancies = []
    last_liters = cfg.get("last_tank_liters", {})
    for c in counters_out:
        tank_id = c["tank_id"]
        if tank_id is None:
            continue
        prev = last_liters.get(str(tank_id))
        current = tank_liters.get(tank_id)
        if prev is not None and current is not None:
            actual_drop = prev - current
            expected_drop = c["sold_liters"]
            diff = round(actual_drop - expected_drop)
            if abs(diff) > 5:  # порог в 5 литров, можно будет вынести в настройки
                discrepancies.append({"tank_id": tank_id, "diff_liters": diff})

    # 4. Сохраняем отчёт
    shift = {
        "operator_tg_id": tg_id,
        "operator_name": operator_name,
        "tank_liters": tank_liters,
        "counters": counters_out,
        "prices": prices,
        "total_liters": total_liters,
        "total_revenue": total_revenue,
        "discrepancies": discrepancies,
    }
    storage.add_shift(shift)

    # 5. Обновляем состояние станции: новые "было" для счётчиков, новая калибровка котлов
    updated_last_liters = dict(last_liters)
    for tank_id, liters in tank_liters.items():
        updated_last_liters[str(tank_id)] = liters
    storage.update_station_config({
        "counter_values": new_counter_values,
        "last_tank_liters": updated_last_liters,
    })

    # 6. Отправляем отчёт владельцам в Telegram
    bot = request.app["bot"]
    text = _format_shift_message(shift)
    for owner_id in OWNER_IDS:
        try:
            await bot.send_message(owner_id, text)
        except Exception:
            pass

    return web.json_response({"ok": True, "shift": shift})


def _format_shift_message(shift: dict) -> str:
    date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")
    lines = [
        f"📋 Отчёт смены — {date_str}",
        f"Оператор: {shift['operator_name']}",
        "",
    ]
    for c in shift["counters"]:
        if c["tank_id"]:
            lines.append(f"{c['fuel']} ({c['tag']}): {c['sold_liters']} л × {c['price']} = {c['revenue']:,} сум")
    lines.append("")
    lines.append(f"Всего продано: {shift['total_liters']} л")
    lines.append(f"Выручка: {shift['total_revenue']:,} сум")

    if shift["discrepancies"]:
        lines.append("")
        lines.append("⚠️ Расхождения:")
        for d in shift["discrepancies"]:
            lines.append(f"Котёл {d['tank_id']}: {d['diff_liters']:+
