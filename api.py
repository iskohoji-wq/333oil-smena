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

    tank_liters = {}
    for t in body.get("tanks", []):
        tank_id = int(t["tank_id"])
        cm = float(t.get("cm", 0))
        mm = float(t.get("mm", 0))
        tank_liters[tank_id] = liters_from_dip(tank_id, cm, mm)

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
            if abs(diff) > 5:
                discrepancies.append({"tank_id": tank_id, "diff_liters": diff})

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

    updated_last_liters = dict(last_liters)
    for tank_id, liters in tank_liters.items():
        updated_last_liters[str(tank_id)] = liters
    storage.update_station_config({
        "counter_values": new_counter_values,
        "last_tank_liters": updated_last_liters,
    })

    bot = request.app["bot"]
    text = _format_shift_message(shift)
    for owner_id in OWNER_IDS:
        try:
            await bot.send_message(owner_id, text)
        except Exception:
            pass

    return web.json_response({"ok": True, "shift": shift})


def _format_shift_message(shift):
    date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")
    lines = []
    lines.append("Отчёт смены — " + date_str)
    lines.append("Оператор: " + str(shift["operator_name"]))
    lines.append("")
    for c in shift["counters"]:
        if c["tank_id"]:
            row = str(c["fuel"]) + " (" + str(c["tag"]) + "): " + str(c["sold_liters"]) + " л x " + str(c["price"]) + " = " + str(c["revenue"]) + " sum"
            lines.append(row)
    lines.append("")
    lines.append("Всего продано: " + str(shift["total_liters"]) + " л")
    lines.append("Выручка: " + str(shift["total_revenue"]) + " сум")

    if shift["discrepancies"]:
        lines.append("")
        lines.append("Расхождения:")
        for d in shift["discrepancies"]:
            row = "Котёл " + str(d["tank_id"]) + ": " + str(d["diff_liters"]) + " л"
            lines.append(row)

    return "\n".join(lines)


async def get_pending(request: web.Request):
    tg_id = request.query.get("tg_id")
    if not _is_owner(tg_id):
        return web.json_response({"error": "not_authorized"}, status=403)
    pending = storage.get_pending()
    return web.json_response([
        {"tg_id": tid, **p} for tid, p in pending.items()
    ])


async def resolve_pending(request: web.Request):
    body = await request.json()
    tg_id = request.query.get("tg_id")
    if not _is_owner(tg_id):
        return web.json_response({"error": "not_authorized"}, status=403)

    target_id = int(body["tg_id"])
    approve = bool(body.get("approve"))
    pending = storage.get_pending().get(str(target_id))
    if not pending:
        return web.json_response({"error": "not_found"}, status=404)

    storage.remove_pending(target_id)
    bot = request.app["bot"]
    if approve:
        storage.add_operator(target_id, pending["name"], pending["phone"])
        try:
            await bot.send_message(target_id, "Владелец одобрил вашу заявку. Теперь вы можете сдавать смены в 333 OIL.")
        except Exception:
            pass
    else:
        try:
            await bot.send_message(target_id, "К сожалению, владелец отклонил вашу заявку.")
        except Exception:
            pass

    return web.json_response({"ok": True})


async def update_settings(request: web.Request):
    tg_id = request.query.get("tg_id")
    if not _is_owner(tg_id):
        return web.json_response({"error": "not_authorized"}, status=403)
    body = await request.json()
    cfg = storage.update_station_config(body)
    return web.json_response(cfg)


def create_app(bot):
    app = web.Application(middlewares=[cors_middleware()])
    app["bot"] = bot
    app.router.add_get("/api/config", get_config)
    app.router.add_post("/api/shift", submit_shift)
    app.router.add_get("/api/pending", get_pending)
    app.router.add_post("/api/pending/resolve", resolve_pending)
    app.router.add_post("/api/settings", update_settings)
    app.router.add_route("OPTIONS", "/{tail:.*}", lambda r: web.Response())
    return app
