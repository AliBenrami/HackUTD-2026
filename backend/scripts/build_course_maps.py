"""Build bundled hole maps from OpenStreetMap for the Dallas area.

Writes mobile/src/data/courseMaps.json and mobile/supabase/mapped_courses.sql.
Yardages are the map distance from the tee to the green. Rating and slope are
left empty because OpenStreetMap does not publish them.
"""

from __future__ import annotations

import json
import math
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = ROOT / "mobile" / "src" / "data" / "courseMaps.json"
OUT_SQL = ROOT / "mobile" / "supabase" / "mapped_courses.sql"
BBOX = (32.85, -96.95, 33.15, -96.55)  # south, west, north, east
QUERY = f"""
[out:json][timeout:180];
(
  way["leisure"="golf_course"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  relation["leisure"="golf_course"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  way["golf"~"^(hole|fairway|green|tee|bunker)$"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
);
out geom;
"""
PREFERRED = (
    "sherrill",
    "firewheel",
    "pecan hollow",
    "duck creek",
    "watters",
    "ridgeview",
    "luna vista",
    "riverchase",
    "canyon creek",
    "twin creeks",
)
TEE_NAMES = ("Black", "Blue", "White", "Red")
TEE_MARKERS = ("#D7DEE8", "#3B82F6", "#F3F6FA", "#F07167")
METERS_TO_YARDS = 1.0936133


CACHE = Path("/tmp/golf-geom.json")


def fetch() -> dict:
    if CACHE.exists() and CACHE.stat().st_size > 1000:
        return json.loads(CACHE.read_text())
    request = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=f"data={urllib.request.quote(QUERY)}".encode(),
        headers={"User-Agent": "GolfAR/1.0 (hackathon course maps)"},
    )
    with urllib.request.urlopen(request, timeout=240) as response:
        raw = response.read()
    CACHE.write_bytes(raw)
    return json.loads(raw.decode())


def ring(element: dict) -> list[dict]:
    if element.get("geometry"):
        return [{"lng": point["lon"], "lat": point["lat"]} for point in element["geometry"]]
    return []


def centroid(points: list[dict]) -> dict | None:
    if not points:
        return None
    return {
        "lng": sum(point["lng"] for point in points) / len(points),
        "lat": sum(point["lat"] for point in points) / len(points),
    }


def yards(a: dict, b: dict) -> float:
    radius = 6371000 * METERS_TO_YARDS
    phi1 = math.radians(a["lat"])
    phi2 = math.radians(b["lat"])
    dphi = math.radians(b["lat"] - a["lat"])
    dlng = math.radians(b["lng"] - a["lng"])
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(min(1, math.sqrt(h)))


def rdp(points: list[dict], epsilon: float) -> list[dict]:
    if len(points) < 3:
        return points

    def dist(point, start, end) -> float:
        if start["lng"] == end["lng"] and start["lat"] == end["lat"]:
            return yards(point, start)
        dx = end["lng"] - start["lng"]
        dy = end["lat"] - start["lat"]
        t = ((point["lng"] - start["lng"]) * dx + (point["lat"] - start["lat"]) * dy) / (dx * dx + dy * dy)
        t = max(0, min(1, t))
        return yards(point, {"lng": start["lng"] + t * dx, "lat": start["lat"] + t * dy})

    pivot = max(range(1, len(points) - 1), key=lambda index: dist(points[index], points[0], points[-1]))
    if dist(points[pivot], points[0], points[-1]) > epsilon:
        return rdp(points[: pivot + 1], epsilon)[:-1] + rdp(points[pivot:], epsilon)
    return [points[0], points[-1]]


def simplify(points: list[dict], epsilon: float, close: bool) -> list[dict]:
    if len(points) < 2:
        return points
    body = points
    closed = close and points[0] == points[-1]
    if closed:
        body = points[:-1]
    simplified = rdp(body if not closed else body + [body[0]], epsilon)
    if closed and simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    return simplified


def contains(polygon: list[dict], point: dict) -> bool:
    inside = False
    if len(polygon) < 3:
        return False
    j = len(polygon) - 1
    for i, corner in enumerate(polygon):
        other = polygon[j]
        intersect = (corner["lat"] > point["lat"]) != (other["lat"] > point["lat"]) and point["lng"] < (
            other["lng"] - corner["lng"]
        ) * (point["lat"] - corner["lat"]) / ((other["lat"] - corner["lat"]) or 1e-12) + corner["lng"]
        if intersect:
            inside = not inside
        j = i
    return inside


def slug(name: str, osm_id: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or f"course-{osm_id}"
    return base[:48]


def location_for(tags: dict) -> str:
    city = tags.get("addr:city")
    state = tags.get("addr:state") or "Texas"
    if city:
        return f"{city}, {state}"
    return "Dallas area, Texas"


def tee_end(line: list[dict], green: dict) -> tuple[dict, dict]:
    """Return the tee end, then the green end. The green end is closer to the green."""
    if yards(line[0], green) <= yards(line[-1], green):
        return line[-1], line[0]
    return line[0], line[-1]


def circle(center: dict, radius_yards: float, count: int = 10) -> list[dict]:
    points = []
    lat = math.radians(center["lat"])
    for index in range(count):
        theta = 2 * math.pi * index / count
        north = radius_yards * math.cos(theta)
        east = radius_yards * math.sin(theta)
        points.append(
            {
                "lng": center["lng"] + east / (111320 * math.cos(lat) * METERS_TO_YARDS),
                "lat": center["lat"] + north / (110540 * METERS_TO_YARDS),
            }
        )
    points.append(points[0])
    return points


def build(data: dict) -> list[dict]:
    courses = []
    holes = []
    greens = []
    tees = []
    fairways = []
    bunkers = []
    for element in data.get("elements", []):
        tags = element.get("tags") or {}
        points = ring(element)
        if tags.get("leisure") == "golf_course" and len(points) >= 3:
            courses.append({"id": element["id"], "tags": tags, "ring": points, "center": centroid(points)})
        kind = tags.get("golf")
        item = {"tags": tags, "ring": points, "center": centroid(points)}
        if kind == "hole" and len(points) >= 2:
            holes.append(item)
        elif kind == "green" and len(points) >= 3:
            greens.append(item)
        elif kind == "tee" and item["center"]:
            tees.append(item)
        elif kind == "fairway" and len(points) >= 3:
            fairways.append(item)
        elif kind == "bunker" and len(points) >= 3:
            bunkers.append(item)

    grouped: dict[int, list] = {course["id"]: [] for course in courses}
    for hole in holes:
        middle = hole["ring"][len(hole["ring"]) // 2]
        owner = next((course for course in courses if contains(course["ring"], middle)), None)
        if owner is None and courses:
            owner = min(courses, key=lambda course: yards(course["center"], middle))
            if yards(owner["center"], middle) > 1400:
                owner = None
        if owner:
            grouped[owner["id"]].append(hole)

    built = []
    for course in courses:
        name = course["tags"].get("name")
        if not name:
            continue
        made = holes_for(course, grouped[course["id"]], greens, tees, fairways, bunkers)
        if len(made) < 18:
            continue
        made = made[:18]
        numbers = {hole["number"] for hole in made}
        if numbers != set(range(1, 19)):
            continue
        built.append(course_document(course, made))
    print(f"courses {len(courses)} holes {len(holes)} greens {len(greens)} tees {len(tees)} built {len(built)}")
    built.sort(key=lambda course: (0 if any(word in course["name"].lower() for word in PREFERRED) else 1, course["name"]))
    return built[:3]


def holes_for(course, raw_holes, greens, tees, fairways, bunkers) -> list[dict]:
    by_number: dict[int, dict] = {}
    for raw in raw_holes:
        try:
            number = int(raw["tags"].get("ref", ""))
            par = int(raw["tags"].get("par", ""))
        except ValueError:
            continue
        if number < 1 or number > 18 or par not in (3, 4, 5):
            continue
        line = raw["ring"]
        green = nearest(greens, line[-1], 100) or nearest(greens, line[0], 100)
        if green is None:
            start, end = line[0], line[-1]
            green_center = end
            green_ring = circle(end, 12)
        else:
            green_center = green["center"]
            start, end = tee_end(line, green_center)
            green_ring = simplify(green["ring"], 3, True)
            if len(green_ring) < 4:
                green_ring = circle(green_center, 12)
        if yards(end, green_center) > 120:
            continue
        candidates = [tee for tee in tees if tee["center"] and yards(tee["center"], start) <= 110]
        if not candidates:
            candidates = [{"center": start, "ring": [start]}]
        buckets: dict[int, dict] = {}
        for tee in candidates:
            distance = yards(tee["center"], green_center)
            if distance < 60:
                continue
            buckets.setdefault(round(distance / 12), tee)
        ordered = sorted(buckets.values(), key=lambda tee: yards(tee["center"], green_center), reverse=True)[:4]
        if not ordered:
            continue
        fairway = next((item for item in fairways if contains(item["ring"], line[len(line) // 2])), None)
        if fairway and yards(fairway["center"], line[len(line) // 2]) > 250:
            fairway = None
        hazard = [
            simplify(item["ring"], 4, True)
            for item in bunkers
            if item["center"] and min(yards(item["center"], point) for point in (start, line[len(line) // 2], end)) <= 70
        ]
        try:
            handicap = int(raw["tags"].get("handicap", ""))
        except ValueError:
            handicap = 0
        hole = {
            "number": number,
            "par": par,
            "handicap": handicap if 1 <= handicap <= 18 else 0,
            "centerline": simplify(line, 6, False),
            "green": green_ring,
            "greenCenter": {"lng": round(green_center["lng"], 6), "lat": round(green_center["lat"], 6)},
            "fairway": simplify(fairway["ring"], 8, True) if fairway else None,
            "bunkers": [item for item in hazard if len(item) >= 4][:8],
            "tees": {},
        }
        for index, tee in enumerate(ordered):
            label = TEE_NAMES[index] if len(ordered) > 1 else "White"
            hole["tees"][label] = {
                "lng": round(tee["center"]["lng"], 6),
                "lat": round(tee["center"]["lat"], 6),
                "yards": int(round(yards(tee["center"], green_center))),
            }
        if number not in by_number or len(hole["tees"]) > len(by_number[number]["tees"]):
            by_number[number] = hole
    holes = [by_number[number] for number in sorted(by_number)]
    assign_handicaps(holes)
    return holes


def nearest(items, point, limit):
    found = [item for item in items if item["center"] and yards(item["center"], point) <= limit]
    if not found:
        return None
    return min(found, key=lambda item: yards(item["center"], point))


def assign_handicaps(holes: list[dict]) -> None:
    tagged = [hole["handicap"] for hole in holes]
    if sorted(tagged) == list(range(1, len(holes) + 1)):
        return
    ranking = sorted(holes, key=lambda hole: max(tee["yards"] for tee in hole["tees"].values()), reverse=True)
    for index, hole in enumerate(ranking, start=1):
        hole["handicap"] = index


def course_document(course, holes: list[dict]) -> dict:
    name = course["tags"]["name"]
    course_id = slug(name, course["id"])
    labels = []
    for hole in holes:
        for label in hole["tees"]:
            if label not in labels:
                labels.append(label)
    order = [label for label in TEE_NAMES if label in labels] or ["White"]
    tee_sets = []
    for index, label in enumerate(order):
        tee_sets.append(
            {
                "id": f"{course_id}-{label.lower()}",
                "name": label,
                "marker": TEE_MARKERS[TEE_NAMES.index(label)],
                "rating": None,
                "slope": None,
                "holes": [
                    {
                        "number": hole["number"],
                        "par": hole["par"],
                        "handicap": hole["handicap"],
                        "yards": hole["tees"].get(label, next(iter(hole["tees"].values())))["yards"],
                    }
                    for hole in holes
                ],
            }
        )
    maps = []
    for hole in holes:
        maps.append(
            {
                "number": hole["number"],
                "tees": hole["tees"],
                "green": hole["green"],
                "greenCenter": hole["greenCenter"],
                "fairway": hole["fairway"],
                "bunkers": hole["bunkers"],
                "centerline": hole["centerline"],
            }
        )
    return {
        "id": course_id,
        "name": name,
        "location": location_for(course["tags"]),
        "summary": "Hole shapes, tees, and greens are from OpenStreetMap. Yardage is the map distance from the tee to the middle of the green.",
        "source": "OpenStreetMap",
        "osmId": course["id"],
        "center": {"lng": round(course["center"]["lng"], 6), "lat": round(course["center"]["lat"], 6)},
        "teeSets": tee_sets,
        "holes": maps,
    }


def sql(courses: list[dict]) -> str:
    lines = [
        "-- OpenStreetMap courses used by the mobile hole maps.",
        "-- Run this in the Supabase SQL editor before starting a round on a mapped course.",
        "alter table public.tee_sets alter column rating drop not null;",
        "alter table public.tee_sets alter column slope drop not null;",
        "",
    ]
    for course in courses:
        lines.append(
            "insert into public.courses (id, name, location, summary) values ("
            f"{quote(course['id'])}, {quote(course['name'])}, {quote(course['location'])}, {quote(course['summary'])}) "
            "on conflict (id) do update set name = excluded.name, location = excluded.location, summary = excluded.summary;"
        )
        for index, tee in enumerate(course["teeSets"]):
            lines.append(
                "insert into public.tee_sets (id, course_id, name, marker, rating, slope, sort_order) values ("
                f"{quote(tee['id'])}, {quote(course['id'])}, {quote(tee['name'])}, {quote(tee['marker'])}, null, null, {index}) "
                "on conflict (id) do update set name = excluded.name, marker = excluded.marker, sort_order = excluded.sort_order;"
            )
            for hole in tee["holes"]:
                lines.append(
                    "insert into public.holes (tee_set_id, hole_number, par, yards, handicap) values ("
                    f"{quote(tee['id'])}, {hole['number']}, {hole['par']}, {hole['yards']}, {hole['handicap']}) "
                    "on conflict (tee_set_id, hole_number) do update set par = excluded.par, yards = excluded.yards, handicap = excluded.handicap;"
                )
        lines.append("")
    return "\n".join(lines)


def quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> None:
    print("Downloading OpenStreetMap golf geometry…")
    courses = build(fetch())
    if not courses:
        raise SystemExit("No complete 18-hole courses were mapped in this area.")
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "attribution": "© OpenStreetMap contributors",
                "courses": courses,
            },
            separators=(",", ":"),
        )
    )
    OUT_SQL.write_text(sql(courses))
    print(f"Wrote {len(courses)} courses to {OUT_JSON}")
    for course in courses:
        print(f"  {course['name']} ({course['id']})")


if __name__ == "__main__":
    main()
