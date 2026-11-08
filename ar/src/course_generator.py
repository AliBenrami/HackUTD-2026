"""Deterministic continuous cyberpunk tabletop terrain generation.

Layouts are render-independent JSON. Coordinates and heights are authored in
course-local metres; the existing ``course-scale-root`` converts them to final
table-local metres exactly once. The visual mesh, collision mesh, height
queries and validator all call :func:`terrain_height`.
"""
from __future__ import annotations

import math
import random

from golf_specs import (BALL_DIAMETER_M, BALL_DIAMETER_MAX_M,
                        BALL_DIAMETER_MIN_M, COURSE_SCALE, COURSE_SCALE_MAX,
                        COURSE_SCALE_MIN, FAIRWAY_WIDTH_EASY_M,
                        FAIRWAY_WIDTH_HARD_M, FAIRWAY_WIDTH_MEDIUM_M)

GRID_SIZE = 97
SAFETY = .003
DIFFICULTIES = {
    "easy": {"waypoints": 2, "bend": .035, "width": FAIRWAY_WIDTH_EASY_M,
             "height": .022, "route_height": .006, "obstacles": 0,
             "hazards": 1, "archetypes": ("neon-straight", "gentle-arc")},
    "medium": {"waypoints": 3, "bend": .075, "width": FAIRWAY_WIDTH_MEDIUM_M,
               "height": .040, "route_height": .014, "obstacles": 2,
               "hazards": 2, "archetypes": ("s-curve", "raised-district")},
    "hard": {"waypoints": 4, "bend": .105, "width": FAIRWAY_WIDTH_HARD_M,
             "height": .055, "route_height": .025, "obstacles": 4,
             "hazards": 3, "archetypes": ("plasma-gauntlet", "ridge-run")},
}
DECOR_ASSETS = ("cyber_tower_block", "cyber_noodle_shop",
                "cyber_vending_kiosk", "cyber_holo_billboard",
                "cyber_server_rack", "cyber_arcade_cabinet",
                "cyber_power_generator", "cyber_neon_sign_vertical",
                "cyber_delivery_drone", "cyber_hover_car")


def _dist(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])


def _segment_projection(x, y, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    t = max(0., min(1., ((x-a[0])*dx+(y-a[1])*dy) /
                        max(1e-12, dx*dx+dy*dy)))
    p = (a[0]+dx*t, a[1]+dy*t)
    return _dist((x, y), p), t, p


def _route_projection(x, y, route):
    lengths = [_dist(a, b) for a, b in zip(route, route[1:])]
    total = max(1e-9, sum(lengths))
    best = (float("inf"), 0., route[0])
    walked = 0.
    for a, b, length in zip(route, route[1:], lengths):
        d, t, p = _segment_projection(x, y, a, b)
        if d < best[0]:
            best = (d, (walked+t*length)/total, p)
        walked += length
    return best


def _smooth(points, passes=3):
    """Chaikin curve with endpoints retained; deterministic and overshoot-free."""
    out = [tuple(p) for p in points]
    for _ in range(passes):
        nxt = [out[0]]
        for a, b in zip(out, out[1:]):
            nxt.extend(((a[0]*.75+b[0]*.25, a[1]*.75+b[1]*.25),
                        (a[0]*.25+b[0]*.75, a[1]*.25+b[1]*.75)))
        nxt.append(out[-1])
        out = nxt
    return [[round(x, 6), round(y, 6)] for x, y in out]


def _hash(seed, x, y):
    n = (x * 374761393 + y * 668265263 + seed * 1442695041) & 0xffffffff
    n = (n ^ (n >> 13)) * 1274126177 & 0xffffffff
    return ((n ^ (n >> 16)) & 0xffff) / 32767.5 - 1.


def _noise(seed, x, y):
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x-ix, y-iy
    sx, sy = fx*fx*(3-2*fx), fy*fy*(3-2*fy)
    a = _hash(seed, ix, iy)*(1-sx)+_hash(seed, ix+1, iy)*sx
    b = _hash(seed, ix, iy+1)*(1-sx)+_hash(seed, ix+1, iy+1)*sx
    return a*(1-sy)+b*sy


def _smoothstep(edge0, edge1, value):
    t = max(0., min(1., (value-edge0)/max(1e-9, edge1-edge0)))
    return t*t*(3-2*t)


def fairway_width_at(layout, progress):
    """Smooth local corridor width with compact, comfortable landing pads."""
    core = layout["fairway_width_m"]
    # Widen only the first/last 9% and blend with a C1-continuous curve.
    endpoint = min(max(0., progress), max(0., 1.-progress))
    landing = 1. - _smoothstep(.025, .095, endpoint)
    return core * (1. + .16*landing)


def terrain_normal(layout, x, y, epsilon=None):
    """Normalized final-heightfield normal in course-local coordinates."""
    if epsilon is None:
        terrain = layout["terrain"]
        epsilon = min(terrain["width_m"], terrain["length_m"]) / \
            max(32, terrain["grid_size"]-1)
    dx = (terrain_height(layout, x+epsilon, y)-
          terrain_height(layout, x-epsilon, y))/(2*epsilon)
    dy = (terrain_height(layout, x, y+epsilon)-
          terrain_height(layout, x, y-epsilon))/(2*epsilon)
    inv = 1./math.sqrt(dx*dx+dy*dy+1.)
    return (-dx*inv, -dy*inv, inv)


def _terrain_field(layout, nx, ny):
    """Low-frequency warped macro terrain plus intentional seeded features."""
    seed = layout["seed"]
    # Low-frequency domain warp breaks axis-aligned/repeating noise contours.
    wx = _noise(seed+401, nx*1.35+.7, ny*1.35-.4) * .16
    wy = _noise(seed+509, nx*1.35-1.1, ny*1.35+.8) * .16
    qx, qy = nx+wx, ny+wy
    macro = 0.
    for octave, weight in enumerate((.64, .25, .11)):
        freq = 1.15*(2**octave)
        macro += _noise(seed+octave*97, qx*freq, qy*freq) * weight
    # A single broad, angled feature reads as a designed ridge rather than
    # corrugation. Seed hashes choose its angle and offset deterministically.
    angle = (_hash(seed+733, 3, 9)+1.) * math.pi
    offset = _hash(seed+811, 7, 2)*.24
    across = (nx-.5)*math.cos(angle)+(ny-.5)*math.sin(angle)-offset
    along = -(nx-.5)*math.sin(angle)+(ny-.5)*math.cos(angle)
    ridge = math.exp(-(across/.075)**2) * math.exp(-(along/.44)**4)
    field = .70*macro + .30*ridge
    # A beveled corner mesa and an opposite service basin give the diorama two
    # deliberate silhouettes without pushing the playable corridor off-level.
    corner = int(_hash(seed+907, 1, 4)*4) % 4
    cx = .18 if corner in (0, 3) else .82
    cy = .18 if corner in (0, 1) else .82
    shelf_d = max(abs(nx-cx)-.18, abs(ny-cy)-.14)
    shelf = 1. - _smoothstep(-.008, .035, shelf_d)
    basin_d = max(abs(nx-(1-cx))-.18, abs(ny-(1-cy))-.13)
    basin = 1. - _smoothstep(-.008, .040, basin_d)
    field = field*(1-shelf*.88) + shelf*.94
    field = field*(1-basin*.60) + basin*.04
    return field


def terrain_height(layout, x, y):
    """Course-local height shared by render, collision and validation."""
    terrain = layout["terrain"]
    route = layout["route"]
    d, t, _ = _route_projection(x, y, route)
    width = fairway_width_at(layout, t)
    amp = terrain["height_amplitude_m"]
    # Broad warped terrain outside the route; no independent vertex noise.
    nx = x / terrain["width_m"] + .5
    ny = y / terrain["length_m"] + .5
    outside = terrain["base_height_m"] + amp*_terrain_field(layout, nx, ny)
    route_z = (terrain["base_height_m"] +
               terrain["route_height_m"] * math.sin(math.pi*t) ** 2)
    # Flat corridor core, smooth cubic blend into noisier industrial terrain.
    blend = _smoothstep(width*.32, width*.62, d)
    # Flatten start and target pads.
    endpoint = min(_dist((x, y), route[0]), _dist((x, y), route[-1]))
    if endpoint < width*.42:
        blend *= _smoothstep(0., width*.42, endpoint)
        route_z = terrain["base_height_m"]
    return route_z*(1-blend)+outside*blend


def height_and_slope(layout, x, y, epsilon=.002):
    z = terrain_height(layout, x, y)
    dx = (terrain_height(layout, x+epsilon, y)-
          terrain_height(layout, x-epsilon, y))/(2*epsilon)
    dy = (terrain_height(layout, x, y+epsilon)-
          terrain_height(layout, x, y-epsilon))/(2*epsilon)
    return z, math.hypot(dx, dy)


def interference(obstacle, route, ball_radius=BALL_DIAMETER_M/2, safety=SAFETY):
    x, y, _ = obstacle["position"]
    d, _, _ = _route_projection(x, y, route)
    expanded = obstacle["footprint_m"]/2 + ball_radius + safety
    if d <= expanded*.65:
        return "directly obstructing"
    if d < expanded:
        return "partially obstructing"
    if d < expanded+.018:
        return "peripheral"
    return "decorative"


def _reserved(x, y, radius, reserved):
    return any(abs(x-rx) < radius+rhx and abs(y-ry) < radius+rhy
               for rx, ry, rhx, rhy in reserved)


def generate(seed, width_m, length_m, difficulty="medium", edge_margin_m=.03,
             decoration_count=6, course_scale=COURSE_SCALE, reserved=(),
             grid_size=GRID_SIZE, ball_diameter_m=BALL_DIAMETER_M):
    if difficulty not in DIFFICULTIES:
        raise ValueError("difficulty must be easy, medium or hard")
    if not COURSE_SCALE_MIN <= course_scale <= COURSE_SCALE_MAX:
        raise ValueError("course_scale outside live range")
    if width_m < .24 or length_m < .18:
        raise ValueError("table too small for cyber golf terrain")
    if not 17 <= grid_size <= 129 or grid_size % 2 == 0:
        raise ValueError("grid_size must be odd and in 17..129")
    if not BALL_DIAMETER_MIN_M <= ball_diameter_m <= BALL_DIAMETER_MAX_M:
        raise ValueError("ball_diameter_m must be in 0.020..0.043m")
    mode = DIFFICULTIES[difficulty]
    rng = random.Random(int(seed))
    reserved = [tuple(map(float, r)) for r in reserved]
    # Use 90% x 85% of the trusted table, still respecting explicit margin.
    final_w = min(width_m*.90, width_m-2*edge_margin_m)
    final_l = min(length_m*.85, length_m-2*edge_margin_m)
    if final_w <= .20 or final_l <= .12:
        raise ValueError("configured margin leaves no terrain footprint")
    local_w, local_l = final_w/course_scale, final_l/course_scale
    local_width = mode["width"]/course_scale
    count = mode["waypoints"]
    final_points = []
    start_y = rng.uniform(-final_l*.18, final_l*.18)
    end_y = rng.uniform(-final_l*.18, final_l*.18)
    for i in range(count+2):
        t = i/(count+1)
        # Leave room for the widened landing pad plus the ball radius so the
        # fairway never spills over the diorama edge.
        x = -final_w*.38 + final_w*.76*t
        if i == 0:
            y = start_y
        elif i == count+1:
            y = end_y
        else:
            alternating = -1 if i % 2 else 1
            y = alternating*rng.uniform(mode["bend"]*.45, mode["bend"])
            y += rng.uniform(-.012, .012)
            y = max(-final_l*.36, min(final_l*.36, y))
        final_points.append((x, y))
    route_final = _smooth(final_points, 3)
    route = [[round(x/course_scale, 6), round(y/course_scale, 6)]
             for x, y in route_final]
    terrain = {"width_m": local_w, "length_m": local_l,
               "base_height_m": .010/course_scale,
               "height_amplitude_m": mode["height"]/course_scale,
               "route_height_m": mode["route_height"]/course_scale,
               "grid_size": grid_size}
    direct = [route[0], route[-1]]
    obstacles = []
    for i in range(mode["obstacles"]):
        diameter_f = .036 if difficulty == "medium" else .042
        diameter = diameter_f/course_scale
        expanded_f = diameter_f/2+ball_diameter_m/2+SAFETY
        direct_offset_f = expanded_f*(.82 if difficulty == "medium" else .35)
        dax = route_final[-1][0]-route_final[0][0]
        day = route_final[-1][1]-route_final[0][1]
        dlen = math.hypot(dax, day) or 1.
        nx, ny = -day/dlen, dax/dlen
        candidates = []
        for step in range(9):
            frac = .18+step*.08
            bx = route_final[0][0]+dax*frac
            by = route_final[0][1]+day*frac
            for side in (-1, 1):
                cx, cy = bx+nx*direct_offset_f*side, by+ny*direct_offset_f*side
                route_distance = _route_projection(cx/course_scale,
                                                   cy/course_scale, route)[0]*course_scale
                separation = min((_dist((cx, cy),
                                  (o["position"][0]*course_scale,
                                   o["position"][1]*course_scale))
                                  for o in obstacles), default=1.)
                if route_distance >= expanded_f+.002 and separation >= diameter_f*.82:
                    candidates.append((route_distance, cx, cy))
        if not candidates:
            continue
        _clearance, xf, yf = max(candidates)
        x, y = xf/course_scale, yf/course_scale
        if _reserved(x*course_scale, y*course_scale,
                     diameter*course_scale/2, reserved):
            continue
        z = terrain_height({"terrain": terrain, "route": route,
                            "fairway_width_m": local_width, "seed": seed}, x, y)
        obstacles.append({"kind": "barrier" if i % 2 else "crystal",
                          "position": [round(x, 6), round(y, 6), round(z, 6)],
                          "footprint_m": diameter,
                          "target": ["xy", diameter]})
    hazards = []
    for i in range(mode["hazards"]):
        t = (i+1)/(mode["hazards"]+1)
        p = route_final[min(len(route_final)-1, round(t*(len(route_final)-1)))]
        side = -1 if (i+seed) % 2 else 1
        radius_f = rng.uniform(.030, .045)
        offset = mode["width"]*.62 + radius_f*(.65 if difficulty == "hard" else 1.05)
        hx, hy = p[0], p[1]+side*offset
        hx = max(-final_w/2+radius_f, min(final_w/2-radius_f, hx))
        hy = max(-final_l/2+radius_f, min(final_l/2-radius_f, hy))
        if _reserved(hx, hy, radius_f, reserved):
            hy = max(-final_l/2+radius_f,
                     min(final_l/2-radius_f, p[1]-side*offset))
        if _reserved(hx, hy, radius_f, reserved):
            continue
        hz = terrain_height({"terrain": terrain, "route": route,
                             "fairway_width_m": local_width, "seed": seed},
                            hx/course_scale, hy/course_scale)
        hazards.append({"kind": "plasma", "position": [hx/course_scale,
                        hy/course_scale, hz+.002/course_scale],
                        "radius_m": radius_f/course_scale,
                        "footprint_m": radius_f*2/course_scale})
    decor = []
    for i in range(decoration_count):
        for _ in range(40):
            x = rng.uniform(-final_w*.44, final_w*.44)
            y = rng.uniform(-final_l*.42, final_l*.42)
            d, _, _ = _route_projection(x/course_scale, y/course_scale, route)
            size = rng.uniform(.018, .034)
            if d*course_scale < mode["width"]*.85+size/2:
                continue
            if _reserved(x, y, size/2, reserved):
                continue
            asset = rng.choice(DECOR_ASSETS)
            z = terrain_height({"terrain": terrain, "route": route,
                                "fairway_width_m": local_width, "seed": seed},
                               x/course_scale, y/course_scale)
            _d, _t, nearest = _route_projection(x/course_scale,
                                                y/course_scale, route)
            # Upright street-facing placement: +Y points approximately toward
            # the route instead of arbitrary diagonal rotations.
            heading = math.degrees(math.atan2(nearest[0]-x/course_scale,
                                              nearest[1]-y/course_scale))
            decor.append({"asset": asset, "position": [x/course_scale,
                          y/course_scale, z], "rotation": [round(heading/15)*15, 0, 0],
                          "target": ["max", size], "footprint_m": size/course_scale})
            break
    layout = {"scene": "cyber-golf", "version": 5, "seed": int(seed),
              "difficulty": difficulty, "course_scale": float(course_scale),
              "table_m": [float(width_m), float(length_m)],
              "margin_m": float(edge_margin_m),
              "ball_diameter_m": float(ball_diameter_m),
              "archetype": rng.choice(mode["archetypes"]),
              "terrain": terrain, "fairway_width_m": local_width,
              "route": route, "direct_route": direct, "reference_route": direct,
              "start": route[0], "hole": route[-1], "obstacles": obstacles,
              "hazards": hazards, "decor": decor,
              "objects": obstacles+hazards+decor, "surfaces": [],
              "segments": len(route)-1, "turns": count,
              "fallback": False, "generation_attempts": {"route": 1, "terrain": 1}}
    valid, detail = validate(layout)
    if not valid:
        raise ValueError(f"invalid generated cyber course: {detail}")
    layout["validation"] = detail
    layout["preferred_route"] = route_search(layout)
    return layout


def validate(layout, course_scale=None):
    try:
        if layout.get("scene") != "cyber-golf" or layout.get("version") != 5:
            return False, "not a cyber-golf v5 layout"
        scale = float(course_scale if course_scale is not None else layout["course_scale"])
        if not COURSE_SCALE_MIN <= scale <= COURSE_SCALE_MAX:
            return False, "course scale outside live range"
        tw, tl = layout["table_m"]
        terrain = layout["terrain"]
        if terrain["width_m"]*scale > tw+.0001 or terrain["length_m"]*scale > tl+.0001:
            return False, "terrain outside table"
        if len(layout["route"]) < 8:
            return False, "route insufficiently sampled"
        ball_diameter = float(layout["ball_diameter_m"])
        if not BALL_DIAMETER_MIN_M <= ball_diameter <= BALL_DIAMETER_MAX_M:
            return False, "ball diameter outside supported range"
        ball_radius = ball_diameter/2
        clearance = layout["fairway_width_m"]*scale/2-ball_radius-SAFETY
        if clearance <= ball_radius*.65:
            return False, "fairway lacks ball-radius clearance"
        slopes = []
        route = layout["route"]
        for p in route[::max(1, len(route)//20)]:
            z, slope = height_and_slope(layout, p[0], p[1], .002/scale)
            slopes.append(slope)
            if not math.isfinite(z+slope):
                return False, "non-finite terrain"
        # Gradient (rise/run) limits include cross-slope at curved corridor
        # edges; route-center elevation remains substantially gentler.
        limit = {"easy": .60, "medium": .85, "hard": 1.15}[layout["difficulty"]]
        if max(slopes, default=0) > limit:
            return False, "route slope exceeds difficulty limit"
        for item in layout["objects"]:
            x, y, _ = item["position"]
            fp = item.get("footprint_m", 0.)
            if abs(x)+fp/2 > terrain["width_m"]/2+.001 or \
               abs(y)+fp/2 > terrain["length_m"]/2+.001:
                return False, "object outside terrain"
        direct_classes = [interference(o, layout["direct_route"],
                                      ball_radius/scale, SAFETY/scale)
                          for o in layout["obstacles"]]
        if layout["difficulty"] == "easy" and direct_classes:
            return False, "easy direct route obstructed"
        if layout["difficulty"] == "medium" and \
                "partially obstructing" not in direct_classes:
            return False, "medium lacks partial obstruction"
        if layout["difficulty"] == "hard" and \
                "directly obstructing" not in direct_classes:
            return False, "hard lacks direct obstruction"
        # The authored spline is the guaranteed ball-centre route. Every
        # blocker must remain outside its swept ball-radius envelope.
        for obstacle in layout["obstacles"]:
            x, y, _ = obstacle["position"]
            distance, _, _ = _route_projection(x, y, route)
            required = obstacle["footprint_m"]/2 + ball_radius/scale + SAFETY/scale
            if distance < required:
                return False, "obstacle blocks preferred route"
        route_len = sum(_dist(a, b) for a, b in zip(route, route[1:]))*scale
        direct_len = _dist(route[0], route[-1])*scale
        return True, {"route_length_m": round(route_len, 3),
                      "direct_length_m": round(direct_len, 3),
                      "max_route_slope": round(max(slopes, default=0), 3),
                      "interference": direct_classes,
                      "terrain_m": [round(terrain["width_m"]*scale, 3),
                                    round(terrain["length_m"]*scale, 3)],
                      "grid": terrain["grid_size"],
                      "ball_diameter_m": ball_diameter,
                      "fairway_width_m": layout["fairway_width_m"]*scale,
                      "course_scale": scale}
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        return False, str(exc)


def route_search(layout, course_scale=None):
    valid, _ = validate(layout, course_scale)
    return [list(p) for p in layout["route"]] if valid else None


def signature(layout):
    return (layout["difficulty"], layout["archetype"],
            tuple((round(x, 4), round(y, 4)) for x, y in layout["route"]),
            tuple((o["kind"], round(o["position"][0], 3),
                   round(o["position"][1], 3)) for o in layout["obstacles"]),
            tuple((round(h["position"][0], 3), round(h["position"][1], 3))
                  for h in layout["hazards"]))
