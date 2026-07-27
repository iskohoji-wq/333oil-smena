"""
HTTP API для Mini App (оператор + владелец), с поддержкой нескольких станций.

Все "тяжёлые" расчёты (литры по калибровке, продано по счётчикам, выручка,
расхождения) считаются ЗДЕСЬ, на сервере — Mini App присылает только сырые
цифры (см/мм, показания счётчиков), а не готовую сумму. Оператор не может
исказить итог на своей стороне ни случайно, ни намеренно.
"""
import json
from datetime import datetime, timezone

from aiohttp import web

import storage
from calibration import TANKS, COUNTER_TO_TANK, liters_from_dip, tank_name
from config import OWNER_IDS, GEMINI_API_KEY


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


def _station_for_request(request: web.Request, tg_id: str) -> str:
    if _is_owner(tg_id):
        return request.query.get("station_id") or storage.DEFAULT_STATION_ID
    return storage.get_operator_station(int(tg_id))


async def get_stations(request: web.Request):
    tg_id = request.query.get("tg_id")
    if not _is_owner(tg_id):
        return web.json_response({"error": "not_authorized"}, status=403)
    stations = storage.get_stations()
    return web.json_response([
        {"id": sid, "name": cfg["name"], "counters_initialized": cfg["counters_initialized"]}
        for sid, cfg in stations.items()
    ])


async def create_station(request: web.Request):
    tg_id = request.query.get("tg_id")
    if not _is_owner(tg_id):
        return web.json_response({"error": "not_authorized"}, status=403)
    body = await request.json()
    station_id = body.get("station_id", "").strip()
    name = body.get("name", "").strip()
    if not station_id or not name:
        return web.json_response({"error": "station_id_and_name_required"}, status=400)
    cfg = storage.create_station(station_id, name)
    return web.json_response(cfg)


async def rename_station(request: web.Request):
    tg_id = request.query.get("tg_id")
    if not _is_owner(tg_id):
        return web.json_response({"error": "not_authorized"}, status=403)
    body = await request.json()
    station_id = body.get("station_id", "").strip()
    name = body.get("name", "").strip()
    if not station_id or not name:
        return web.json_response({"error": "station_id_and_name_required"}, status=400)
    cfg = storage.rename_station(station_id, name)
    return web.json_response(cfg)


async def get_config(request: web.Request):
    tg_id = request.query.get("tg_id")
    lang = storage.get_lang(int(tg_id)) if tg_id and tg_id.isdigit() else "ru"

    if not tg_id or not (storage.is_operator(int(tg_id)) or _is_owner(tg_id)):
        return web.json_response({"error": "not_authorized"}, status=403)

    station_id = _station_for_request(request, tg_id)
    cfg = storage.get_station(station_id)
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
        "station_id": station_id,
        "station_name": cfg["name"],
        "tanks": tanks_out,
        "counter_tags": cfg["counter_tags"],
        "counter_values": cfg["counter_values"],
        "counters_initialized": cfg["counters_initialized"],
        "counter_to_tank": COUNTER_TO_TANK,
        "prices": cfg["prices"],
    })


async def submit_shift(request: web.Request):
    body = await request.json()
    tg_id = body.get("tg_id")

    if not tg_id or not storage.is_operator(int(tg_id)):
        return web.json_response({"error": "not_authorized"}, status=403)

    station_id = storage.get_operator_station(int(tg_id))
    cfg = storage.get_station(station_id)

    if not cfg.get("counters_initialized"):
        return web.json_response({"error": "counters_not_initialized"}, status=409)

    operators = storage.get_operators()
    operator_name = operators.get(str(tg_id), {}).get("name", "—")

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
        "station_id": station_id,
        "station_name": cfg["name"],
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
    storage.apply_shift_end_counters(station_id, new_counter_values)
    storage.update_station_settings(station_id, {"last_tank_liters": updated_last_liters})

    bot = request.app["bot"]
    text = _format_shift_message(shift)
    delivery_failed_for = []
    for owner_id in OWNER_IDS:
        try:
            await bot.send_message(owner_id, text)
        except Exception:
            delivery_failed_for.append(owner_id)

    return web.json_response({"ok": True, "shift": shift, "delivery_failed_for": delivery_failed_for})


def _format_shift_message(shift: dict) -> str:
    date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")
    lines = [
        "📋 Отчёт смены — " + date_str,
        "Станция: " + shift.get("station_name", "—"),
        "Оператор: " + shift["operator_name"],
        "",
    ]
    for c in shift["counters"]:
        if c["tank_id"]:
            lines.append(c["fuel"] + " (" + c["tag"] + "): " + str(c["sold_liters"]) + " л x " + str(c["price"]) + " = " + format(c["revenue"], ",") + " сум")
    lines.append("")
    lines.append("Всего продано: " + str(shift["total_liters"]) + " л")
    lines.append("Выручка: " + format(shift["total_revenue"], ",") + " сум")

    if shift["discrepancies"]:
        lines.append("")
        lines.append("⚠️ Расхождения:")
        for d in shift["discrepancies"]:
            lines.append("Котёл " + str(d["tank_id"]) + ": " + format(d["diff_liters"], "+") + " л")

    return "\n".join(lines).replace(",", " ")


async def get_reports(request: web.Request):
    tg_id = request.query.get("tg_id")
    if not _is_owner(tg_id):
        return web.json_response({"error": "not_authorized"}, status=403)

    date = request.query.get("date")
    station_id = request.query.get("station_id")
    shifts = storage.get_shifts(station_id=station_id, date=date)

    total_liters = sum(s.get("total_liters", 0) for s in shifts)
    total_revenue = sum(s.get("total_revenue", 0) for s in shifts)

    return web.json_response({
        "date": date,
        "station_id": station_id,
        "shifts": shifts,
        "total_liters": total_liters,
        "total_revenue": total_revenue,
        "archive_days": storage.ARCHIVE_DAYS,
    })


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
    station_id = body.get("station_id", storage.DEFAULT_STATION_ID)
    pending = storage.get_pending().get(str(target_id))
    if not pending:
        return web.json_response({"error": "not_found"}, status=404)

    storage.remove_pending(target_id)
    operator_lang = storage.get_lang(target_id, default="ru")
    bot = request.app["bot"]
    if approve:
        storage.add_operator(target_id, pending["name"], pending["phone"], lang=operator_lang, station_id=station_id)
        text = "✅ Владелец одобрил вашу заявку. Теперь вы можете сдавать смены в 333 OIL." if operator_lang == "ru" \
            else "✅ Egasi so'rovingizni tasdiqladi. Endi 333 OIL'da smena topshirishingiz mumkin."
        try:
            await bot.send_message(target_id, text)
        except Exception:
            pass
    else:
        text = "К сожалению, владелец отклонил вашу заявку." if operator_lang == "ru" \
            else "Afsuski, egasi so'rovingizni rad etdi."
        try:
            await bot.send_message(target_id, text)
        except Exception:
            pass

    return web.json_response({"ok": True})


async def set_initial_counters(request: web.Request):
    tg_id = request.query.get("tg_id")
    if not _is_owner(tg_id):
        return web.json_response({"error": "not_authorized"}, status=403)
    body = await request.json()
    station_id = body.get("station_id", storage.DEFAULT_STATION_ID)
    values = body.get("counter_values", {})
    applied = storage.set_initial_counters(station_id, values)
    if not applied:
        return web.json_response({"error": "already_initialized"}, status=409)
    return web.json_response({"ok": True, "station": storage.get_station(station_id)})


async def update_settings(request: web.Request):
    tg_id = request.query.get("tg_id")
    if not _is_owner(tg_id):
        return web.json_response({"error": "not_authorized"}, status=403)
    body = await request.json()
    station_id = body.pop("station_id", storage.DEFAULT_STATION_ID)
    cfg = storage.update_station_settings(station_id, body)
    return web.json_response(cfg)


async def ai_ask(request: web.Request):
    tg_id = request.query.get("tg_id")
    if not _is_owner(tg_id):
        return web.json_response({"error": "not_authorized"}, status=403)

    if not GEMINI_API_KEY:
        return web.json_response({"error": "ai_not_configured"}, status=503)

    body = await request.json()
    question = body.get("question", "").strip()
    if not question:
        return web.json_response({"error": "question_required"}, status=400)

    lang = storage.get_lang(int(tg_id), default="ru")
    stations = storage.get_stations()
    recent_shifts = storage.get_shifts()[-100:]

    context = {
        "stations": stations,
        "recent_shifts": recent_shifts,
    }

    if lang == "uz":
        system_prompt = (
            "Sen 333 OIL benzin quyish shoxobchalari tarmog'ining sun'iy intellekt "
            "yordamchisisan. Faqat quyida berilgan JSON ma'lumotlar asosida javob ber, "
            "hech narsa o'ylab topma. Javobni FAQAT o'zbek tilida, aniq va lo'nda yoz."
        )
    else:
        system_prompt = (
            "Ты ИИ-ассистент сети АЗС 333 OIL. Отвечай ТОЛЬКО на основе приведённых "
            "ниже данных в формате JSON, ничего не придумывай. Отвечай ТОЛЬКО на "
            "русском языке, чётко и по делу."
        )

    import aiohttp as _aiohttp
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=" + GEMINI_API_KEY
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{
            "parts": [{"text": "Данные станций:\n" + json.dumps(context, ensure_ascii=False) + "\n\nВопрос владельца: " + question}],
        }],
    }
    try:
        async with _aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=_aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
                if resp.status != 200:
                    return web.json_response({"error": "ai_request_failed", "detail": data}, status=502)
    except Exception as e:
        return web.json_response({"error": "ai_request_failed", "detail": str(e)}, status=502)

    try:
        answer = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        answer = ""
    return web.json_response({"answer": answer})


def create_app(bot) -> web.Application:
    app = web.Application(middlewares=[cors_middleware()])
    app["bot"] = bot
    app.router.add_get("/api/config", get_config)
    app.router.add_post("/api/shift", submit_shift)
    app.router.add_get("/api/reports", get_reports)
    app.router.add_get("/api/pending", get_pending)
    app.router.add_post("/api/pending/resolve", resolve_pending)
    app.router.add_post("/api/settings", update_settings)
    app.router.add_post("/api/settings/init-counters", set_initial_counters)
    app.router.add_get("/api/stations", get_stations)
    app.router.add_post("/api/stations/create", create_station)
    app.router.add_post("/api/stations/rename", rename_station)
    app.router.add_post("/api/ai/ask", ai_ask)
    app.router.add_route("OPTIONS", "/{tail:.*}", lambda r: web.Response())
    return app
