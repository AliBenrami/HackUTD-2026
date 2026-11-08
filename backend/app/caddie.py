"""Hole card, round recap, and swing lines.

Gemini is used when GEMINI_API_KEY is set. A checked fallback card is returned
when the model is missing or its JSON does not match the bag.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any
from urllib.request import Request, urlopen

from app.golfstore import get_store, now

PIN_SHIFT = {"front": -8, "middle": 0, "back": 8}
STARTER_BAG = [
    {"name": "Driver", "carry": 230},
    {"name": "3-wood", "carry": 215},
    {"name": "5-iron", "carry": 175},
    {"name": "7-iron", "carry": 155},
    {"name": "9-iron", "carry": 135},
    {"name": "Pitching wedge", "carry": 120},
    {"name": "Sand wedge", "carry": 90},
]
COURSE_POINTS = {
    "cedar-ridge": (32.7767, -96.7970),
    "neon-dunes": (33.4942, -111.9261),
    "harbor-lights": (29.3013, -94.7977),
}


def tendencies_for(user_id: str) -> dict:
    notes = [
        note
        for note in get_store().find("hole_notes", {"userId": user_id})
        if note.get("strokes") and not note.get("sample")
    ]
    by_par: dict[int, list[float]] = {}
    misses = {"left": 0, "right": 0, "short": 0, "long": 0}
    gir_hit = 0
    gir_seen = 0
    for note in notes:
        by_par.setdefault(int(note["par"]), []).append(note["strokes"] - note["par"])
        if note.get("miss") in misses:
            misses[note["miss"]] += 1
        if note.get("gir") in (True, False):
            gir_seen += 1
            gir_hit += 1 if note["gir"] else 0
    return {
        "holes": len(notes),
        "byPar": {str(par): sum(values) / len(values) for par, values in by_par.items()},
        "misses": misses,
        "gir": None if gir_seen == 0 else gir_hit / gir_seen,
        "updatedAt": now(),
    }


def mongo_tendencies(user_id: str) -> dict | None:
    store = get_store()
    aggregate = getattr(store, "aggregate", None)
    if aggregate is None:
        return None
    rows = aggregate(
        "hole_notes",
        [
            {"$match": {"userId": user_id, "sample": False, "strokes": {"$ne": None}}},
            {
                "$facet": {
                    "byPar": [
                        {
                            "$group": {
                                "_id": "$par",
                                "avgToPar": {"$avg": {"$subtract": ["$strokes", "$par"]}},
                                "holes": {"$sum": 1},
                            }
                        }
                    ],
                    "misses": [
                        {"$match": {"miss": {"$in": ["left", "right", "short", "long"]}}},
                        {"$group": {"_id": "$miss", "n": {"$sum": 1}}},
                    ],
                    "gir": [
                        {"$match": {"gir": {"$in": [True, False]}}},
                        {
                            "$group": {
                                "_id": None,
                                "hit": {"$sum": {"$cond": ["$gir", 1, 0]}},
                                "n": {"$sum": 1},
                            }
                        }
                    ],
                }
            },
        ],
    )
    if not rows:
        return None
    facet = rows[0]
    misses = {"left": 0, "right": 0, "short": 0, "long": 0}
    for row in facet.get("misses", []):
        misses[row["_id"]] = row["n"]
    gir_rows = facet.get("gir") or []
    gir = None if not gir_rows or not gir_rows[0]["n"] else gir_rows[0]["hit"] / gir_rows[0]["n"]
    holes = sum(row["holes"] for row in facet.get("byPar", []))
    return {
        "holes": holes,
        "byPar": {str(row["_id"]): row["avgToPar"] for row in facet.get("byPar", [])},
        "misses": misses,
        "gir": gir,
        "updatedAt": now(),
    }


def load_bag(user_id: str) -> dict:
    found = get_store().find("bags", {"userId": user_id})
    if found:
        return found[0]
    bag = {
        "userId": user_id,
        "clubs": [dict(club) for club in STARTER_BAG],
        "handicapIndex": None,
        "tendencies": tendencies_for(user_id),
        "starter": True,
    }
    return get_store().replace("bags", {"userId": user_id}, bag)


def save_bag(user_id: str, clubs: list, handicap_index: float | None) -> dict:
    cleaned = []
    for club in clubs:
        name = str(club.get("name", "")).strip()
        carry = club.get("carry")
        if not name or not isinstance(carry, (int, float)) or carry <= 0 or carry > 400:
            continue
        cleaned.append({"name": name[:40], "carry": int(round(carry))})
    if not cleaned:
        cleaned = [dict(club) for club in STARTER_BAG]
    index = handicap_index if isinstance(handicap_index, (int, float)) and 0 <= handicap_index <= 54 else None
    current = load_bag(user_id)
    document = {
        "userId": user_id,
        "clubs": cleaned,
        "handicapIndex": index,
        "tendencies": current.get("tendencies") or tendencies_for(user_id),
        "starter": False,
    }
    return get_store().replace("bags", {"userId": user_id}, document)


def save_note(user_id: str, note: dict) -> dict:
    hole = int(note["holeNumber"])
    document = {
        "userId": user_id,
        "roundId": str(note["roundId"]),
        "holeNumber": hole,
        "par": int(note["par"]),
        "strokes": note.get("strokes"),
        "sample": bool(note.get("sample")),
        "miss": note.get("miss") if note.get("miss") in ("left", "right", "short", "long") else None,
        "gir": note.get("gir") if note.get("gir") in (True, False) else None,
        "pin": note.get("pin") if note.get("pin") in PIN_SHIFT else "middle",
        "club": note.get("club"),
        "cardId": note.get("cardId"),
        "shots": note.get("shots") if isinstance(note.get("shots"), list) else [],
        "savedAt": now(),
    }
    stored = get_store().replace(
        "hole_notes",
        {"userId": user_id, "roundId": document["roundId"], "holeNumber": hole},
        document,
    )
    stats = mongo_tendencies(user_id) or tendencies_for(user_id)
    bag = load_bag(user_id)
    bag["tendencies"] = stats
    get_store().replace("bags", {"userId": user_id}, bag)
    return stored


def weather(latitude: float, longitude: float) -> dict | None:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        "&current=wind_speed_10m,wind_direction_10m,wind_gusts_10m&wind_speed_unit=mph"
    )
    try:
        with urlopen(url, timeout=8) as response:
            body = json.loads(response.read().decode())
        current = body["current"]
        return {
            "speedMph": current["wind_speed_10m"],
            "gustMph": current.get("wind_gusts_10m"),
            "fromDeg": current["wind_direction_10m"],
        }
    except Exception:
        return None


def course_weather(course_id: str, center: dict | None) -> dict | None:
    if center and "lat" in center and "lng" in center:
        return weather(float(center["lat"]), float(center["lng"]))
    point = COURSE_POINTS.get(course_id)
    if not point:
        return None
    return weather(point[0], point[1])


def _target(hole_yards: int, pin: str, wind: dict | None, wind_on: bool, bearing: float | None) -> tuple[int, str]:
    shift = PIN_SHIFT.get(pin, 0)
    note = ""
    adjust = 0
    if wind_on and wind:
        note, adjust = _wind_phrase(wind, bearing)
    return max(1, int(round(hole_yards + shift + adjust))), note


def _wind_phrase(wind: dict, bearing: float | None) -> tuple[str, int]:
    speed = max(0, int(round(wind["speedMph"])))
    if bearing is None:
        return f"{speed} mph from the {_compass(wind['fromDeg'])}", 0
    delta = abs(wind["fromDeg"] - bearing) % 360
    delta = 360 - delta if delta > 180 else delta
    if delta < 50:
        return f"{speed} mph into you", speed
    if delta > 130:
        return f"{speed} mph downwind", -speed
    side = "right" if math.sin(math.radians(wind["fromDeg"] - bearing)) > 0 else "left"
    return f"{speed} mph from the {side}", 0


def _compass(degrees: float) -> str:
    names = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]
    return names[round(degrees % 360 / 45) % 8]


def _pick(clubs: list, yards: float) -> dict:
    return min(clubs, key=lambda club: abs(club["carry"] - yards))


def fallback_card(clubs: list, hole_yards: int, pin: str, wind: dict | None, wind_on: bool, bearing: float | None, common_miss: str | None) -> dict:
    playing, wind_note = _target(hole_yards, pin, wind, wind_on, bearing)
    club = _pick(clubs or STARTER_BAG, playing)
    wind_adjust = playing - (hole_yards + PIN_SHIFT.get(pin, 0))
    reasons = [f"{club['name']} is the closest club in your bag to {playing} yards."]
    if pin == "front":
        reasons.append("The pin is up, so the target is 8 yards shorter.")
    elif pin == "back":
        reasons.append("The pin is back, so the target is 8 yards longer.")
    return {
        "club": club["name"],
        "carryYards": club["carry"],
        "adjustedYards": int(club["carry"] + wind_adjust),
        "aim": "center",
        "missTo": common_miss or "left",
        "windNote": f"{wind_note}." if wind_note else "",
        "reasons": reasons[:3],
        "assumptions": ["Carries are the bag you entered.", "The model was not used."],
        "confidence": "limited",
        "source": "fallback",
    }


def validate_card(value: Any, clubs: list, fair_allowed: bool) -> dict | None:
    if not isinstance(value, dict):
        return None
    club = next((item for item in clubs if item["name"] == value.get("club")), None)
    if club is None or value.get("carryYards") != club["carry"]:
        return None
    adjusted = value.get("adjustedYards")
    if not isinstance(adjusted, (int, float)) or abs(adjusted - club["carry"]) > 40:
        return None
    if value.get("aim") not in ("center", "left", "right"):
        return None
    if value.get("missTo") not in ("left", "right", "short", "long"):
        return None
    wind_note = value.get("windNote")
    reasons = value.get("reasons")
    assumptions = value.get("assumptions")
    if not isinstance(wind_note, str) or len(wind_note) > 180:
        return None
    if not isinstance(reasons, list) or not 1 <= len(reasons) <= 3:
        return None
    if not all(isinstance(reason, str) and 0 < len(reason) <= 180 for reason in reasons):
        return None
    if not isinstance(assumptions, list) or len(assumptions) > 4:
        return None
    if value.get("confidence") not in ("limited", "fair"):
        return None
    confidence = "fair" if value["confidence"] == "fair" and fair_allowed else "limited"
    return {
        "club": club["name"],
        "carryYards": club["carry"],
        "adjustedYards": int(round(adjusted)),
        "aim": value["aim"],
        "missTo": value["missTo"],
        "windNote": wind_note,
        "reasons": reasons,
        "assumptions": assumptions if all(isinstance(item, str) and len(item) <= 180 for item in assumptions) else [],
        "confidence": confidence,
        "source": "gemini",
    }


CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "club": {"type": "string"},
        "carryYards": {"type": "integer"},
        "adjustedYards": {"type": "integer"},
        "aim": {"type": "string", "enum": ["center", "left", "right"]},
        "missTo": {"type": "string", "enum": ["left", "right", "short", "long"]},
        "windNote": {"type": "string"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["limited", "fair"]},
    },
    "required": ["club", "carryYards", "adjustedYards", "aim", "missTo", "windNote", "reasons", "assumptions", "confidence"],
}

TOOLS = [
    {"name": "get_hole", "description": "Par, yardage, and stroke index for the hole being played.", "parameters": {"type": "object", "properties": {}}},
    {"name": "get_bag", "description": "The player's clubs and entered carry yards.", "parameters": {"type": "object", "properties": {}}},
    {"name": "get_tendencies", "description": "Miss counts and scoring against par from saved holes.", "parameters": {"type": "object", "properties": {}}},
    {"name": "get_weather", "description": "Wind at the course. Empty when wind was not requested.", "parameters": {"type": "object", "properties": {}}},
    {"name": "get_latest_swing", "description": "Elbow angles from the latest filmed swing for the likely club.", "parameters": {"type": "object", "properties": {}}},
]


def _gemini(contents: list, tools: list | None = None, schema: dict | None = None) -> dict | None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    body: dict[str, Any] = {"contents": contents}
    if tools:
        body["tools"] = [{"functionDeclarations": tools}]
    if schema:
        body["generationConfig"] = {"responseMimeType": "application/json", "responseSchema": schema}
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode())
    except Exception:
        return None


def _tool_payload(name: str, context: dict) -> dict:
    if name == "get_hole":
        return context["hole"]
    if name == "get_bag":
        return {"clubs": context["clubs"], "starter": context["starter"]}
    if name == "get_tendencies":
        return context["tendencies"]
    if name == "get_weather":
        return context["weather"] or {"requested": False}
    if name == "get_latest_swing":
        return context["swing"] or {"available": False}
    return {}


def _ask_gemini(context: dict) -> dict | None:
    prompt = (
        "You are preparing one golf hole card. Call the tools, then stop. "
        "Do not write the card yet."
    )
    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    first = _gemini(contents, tools=TOOLS)
    calls = []
    trace = []
    if first:
        parts = ((first.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        calls = [part["functionCall"] for part in parts if "functionCall" in part]
        contents.append({"role": "model", "parts": parts or [{"text": "No tools called."}]})
        responses = []
        for call in calls:
            payload = _tool_payload(call.get("name", ""), context)
            trace.append({"name": call.get("name"), "result": payload})
            responses.append({"functionResponse": {"name": call.get("name", "tool"), "response": payload}})
        if responses:
            contents.append({"role": "user", "parts": responses})
    contents.append(
        {
            "role": "user",
            "parts": [
                {
                    "text": (
                        "Write the card as JSON. The club and carryYards must be copied from the bag. "
                        "adjustedYards stays within 40 yards of that carry. "
                        "This is a suggestion, not a measurement. Give at most three reasons. "
                        f"Facts: {json.dumps(context)}"
                    )
                }
            ],
        }
    )
    second = _gemini(contents, schema=CARD_SCHEMA)
    if not second:
        return None
    text = ""
    for part in ((second.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []:
        text += part.get("text", "")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return {"card": parsed, "trace": trace}


def build_card(user_id: str, request: dict) -> dict:
    bag = load_bag(user_id)
    clubs = bag["clubs"]
    pin = request.get("pin") if request.get("pin") in PIN_SHIFT else "middle"
    wind_on = bool(request.get("windOn"))
    wind = course_weather(request.get("courseId", ""), request.get("center")) if wind_on else None
    bearing = request.get("holeBearing")
    stats = bag.get("tendencies") or tendencies_for(user_id)
    misses = stats.get("misses") or {}
    common = max(misses, key=misses.get) if any(misses.values()) else None
    hole_yards = int(request["yards"])
    context = {
        "hole": {
            "course": request.get("courseName"),
            "hole": request.get("holeNumber"),
            "par": request.get("par"),
            "yards": hole_yards,
            "pin": pin,
            "handicap": request.get("handicap"),
        },
        "clubs": clubs,
        "starter": bag.get("starter", False),
        "tendencies": stats,
        "weather": wind if wind_on else None,
        "swing": request.get("swing"),
    }
    fair = stats.get("holes", 0) >= 10 and (not wind_on or wind is not None)
    model = _ask_gemini(context)
    card = validate_card(model["card"], clubs, fair) if model else None
    if card is None:
        card = fallback_card(clubs, hole_yards, pin, wind, wind_on, bearing, common)
        trace = []
        source = "fallback"
    else:
        trace = model["trace"]
        source = "gemini"
    run = {
        "userId": user_id,
        "roundId": request.get("roundId"),
        "holeNumber": request.get("holeNumber"),
        "source": source,
        "model": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash") if source == "gemini" else None,
        "trace": trace,
        "card": card,
        "createdAt": now(),
    }
    stored = get_store().replace("caddie_runs", {"userId": user_id, "createdAt": run["createdAt"], "holeNumber": run["holeNumber"]}, run)
    card["id"] = stored["createdAt"]
    return card


def similar_swing(user_id: str, video_id: str, vector: list) -> dict:
    best = None
    best_rms = None
    for swing in get_store().find("swings", {"userId": user_id}):
        if swing.get("videoId") == video_id:
            continue
        rms = _rms(vector, swing.get("angleVector") or [])
        if rms is None:
            continue
        if best_rms is None or rms < best_rms:
            best = swing
            best_rms = rms
    if best is None or best_rms is None or best_rms > 25:
        return {"close": False, "reason": "No other filmed swing is close to this one."}
    return {"close": True, "club": best.get("club"), "createdAt": best.get("createdAt"), "rms": round(best_rms, 1)}


def _rms(left: list, right: list) -> float | None:
    diffs = [
        (a - b) ** 2
        for a, b in zip(left, right)
        if isinstance(a, (int, float)) and isinstance(b, (int, float))
    ]
    if len(diffs) < 8:
        return None
    return math.sqrt(sum(diffs) / len(diffs))


def save_swing(user_id: str, body: dict) -> dict:
    document = {
        "userId": user_id,
        "videoId": str(body["videoId"]),
        "club": str(body.get("club") or "Club"),
        "createdAt": now(),
        "angleVector": body.get("angleVector") if isinstance(body.get("angleVector"), list) else [],
        "measured": body.get("measured"),
    }
    return get_store().replace("swings", {"userId": user_id, "videoId": document["videoId"]}, document)


def recap(user_id: str, body: dict) -> dict | None:
    prompt = {
        "score": body.get("summary"),
        "notes": body.get("notes"),
        "cards": body.get("cards"),
        "task": "Write exactly four short lines: the score, where misses clustered, which club kept coming up, and one thing to film next. Do not promise a better score.",
    }
    result = _gemini(
        [{"role": "user", "parts": [{"text": json.dumps(prompt)}]}],
        schema={
            "type": "object",
            "properties": {"lines": {"type": "array", "items": {"type": "string"}}},
            "required": ["lines"],
        },
    )
    lines = None
    if result:
        text = ""
        for part in ((result.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []:
            text += part.get("text", "")
        try:
            parsed = json.loads(text)
            if isinstance(parsed.get("lines"), list):
                lines = [str(line)[:180] for line in parsed["lines"][:4]]
        except json.JSONDecodeError:
            lines = None
    if not lines or len(lines) < 4:
        return None
    document = {"userId": user_id, "roundId": body["roundId"], "lines": lines, "source": "gemini", "createdAt": now()}
    get_store().replace("rounds", {"userId": user_id, "roundId": body["roundId"]}, document)
    return document


def narrate(body: dict) -> dict | None:
    result = _gemini(
        [{"role": "user", "parts": [{"text": json.dumps(body)}]}],
        schema={
            "type": "object",
            "properties": {
                "insights": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "observation": {"type": "string"},
                            "why": {"type": "string"},
                        },
                        "required": ["id", "observation", "why"],
                    },
                }
            },
            "required": ["insights"],
        },
    )
    if not result:
        return None
    text = ""
    for part in ((result.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []:
        text += part.get("text", "")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
