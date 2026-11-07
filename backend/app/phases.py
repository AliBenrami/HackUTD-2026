"""Place Address through Finish from the path of the hands.

Image y grows downward, so the top of the backswing is a valley in y that is
followed by the hands dropping. A finish also lifts the hands. It is not
another swing, because the hands do not drop into a new downswing after it.

The window starts at the takeaway, not at the beginning of the clip, and it
ends on the follow-through. Standing around before the swing is left out.
"""

from __future__ import annotations

PHASES = (
    "Address",
    "Toe-up",
    "Mid-backswing",
    "Top",
    "Mid-downswing",
    "Impact",
    "Mid-follow-through",
    "Finish",
)


def fill_short_gaps(values: list[float | None], limit: int = 4) -> list[float | None]:
    filled = list(values)
    index = 0
    while index < len(filled):
        if filled[index] is not None:
            index += 1
            continue
        start = index
        while index < len(filled) and filled[index] is None:
            index += 1
        gap = index - start
        left = start - 1
        right = index
        if gap > limit or left < 0 or right >= len(filled):
            continue
        left_value = filled[left]
        right_value = filled[right]
        if left_value is None or right_value is None:
            continue
        for step in range(gap):
            weight = (step + 1) / (gap + 1)
            filled[start + step] = left_value * (1 - weight) + right_value * weight
    return filled


def smooth(values: list[float | None], radius: int = 2) -> list[float | None]:
    smoothed: list[float | None] = []
    for index in range(len(values)):
        window = [
            values[cursor]
            for cursor in range(max(0, index - radius), min(len(values), index + radius + 1))
            if values[cursor] is not None
        ]
        smoothed.append(sum(window) / len(window) if window else None)
    return smoothed


def segment_swings(hand_y: list[float | None], *, height: int, fps: float) -> list[list[int]]:
    """Return eight cue frames for each swing found in the hand path."""
    if height <= 0 or fps <= 0 or len(hand_y) < max(8, int(fps * 0.4)):
        return []
    path = smooth(fill_short_gaps(hand_y, limit=max(4, int(0.25 * fps))))
    tops = _tops(path, height=height, fps=fps)
    addresses = [
        _address(path, top, 0 if index == 0 else tops[index - 1] + 1, height=height, fps=fps)
        for index, top in enumerate(tops)
    ]
    swings: list[list[int]] = []
    for index, top in enumerate(tops):
        address = addresses[index]
        following = next((item for item in addresses[index + 1 :] if item is not None), None)
        end = following if following is not None and following > top else len(path)
        cues = _cues(path, address, top, end, height=height, fps=fps)
        if cues is not None:
            swings.append(cues)
    return swings


def _tops(path: list[float | None], *, height: int, fps: float) -> list[int]:
    known = [value for value in path if value is not None]
    if len(known) < 8:
        return []
    lookback = max(3, int(1.8 * fps))
    min_rise = 0.15 * height
    min_sep = max(1, int(0.8 * fps))
    candidates: list[int] = []
    for index in range(1, len(path) - 1):
        current = path[index]
        before = path[index - 1]
        after = path[index + 1]
        if current is None or before is None or after is None:
            continue
        if current > before or current > after:
            continue
        window = [path[cursor] for cursor in range(max(0, index - lookback), index) if path[cursor] is not None]
        if not window or max(window) - current < min_rise:
            continue
        if not _drops_then_rises(path, index, height=height, fps=fps):
            continue
        candidates.append(index)
    chosen: list[int] = []
    for index in sorted(candidates, key=lambda item: (path[item] if path[item] is not None else 0, item)):
        if all(abs(index - kept) >= min_sep for kept in chosen):
            chosen.append(index)
    chosen.sort()
    return chosen


def _drops_then_rises(path: list[float | None], index: int, *, height: int, fps: float) -> bool:
    """A backswing top drops through the ball, then the hands rise into the finish.

    The rise has to follow the drop without a pause. Standing around, then a
    later swing, is not this swing's follow-through. A slow downswing still
    counts, because the search keeps going while the hands are moving.
    """
    peak = path[index]
    if peak is None:
        return False
    min_drop = 0.14 * height
    min_lift = 0.10 * height
    end = min(len(path) - 1, index + max(3, int(2.0 * fps)))
    rest_limit = max(2, int(0.45 * fps))
    low_y = peak
    rest = 0
    for cursor in range(index + 1, end + 1):
        value = path[cursor]
        if value is None:
            continue
        if value > low_y:
            low_y = value
            rest = 0
            continue
        if low_y - peak < min_drop:
            continue
        if value >= low_y - 0.03 * height:
            rest += 1
            if rest > rest_limit:
                return False
            continue
        rest = 0
        if low_y - value >= min_lift:
            return True
    return False


def _address(path: list[float | None], top: int, left: int, *, height: int, fps: float) -> int | None:
    """The last settled frame before the takeaway, not the start of the clip."""
    earliest = max(left, top - int(1.8 * fps))
    peak = path[top]
    if peak is None:
        return None
    indexes = [index for index in range(earliest, top) if path[index] is not None]
    if not indexes:
        return None
    low_y = max(path[index] or 0 for index in indexes)
    if low_y - peak < 0.15 * height:
        return None
    band = 0.05 * height
    near = [index for index in indexes if path[index] is not None and low_y - path[index] <= band]
    if not near:
        return None
    return near[-1]


def _impact(path: list[float | None], top: int, end: int, address_y: float, height: int) -> int | None:
    tolerance = 0.08 * height
    in_band: list[int] = []
    for index in range(top + 1, end):
        value = path[index]
        if value is None:
            continue
        if abs(value - address_y) <= tolerance:
            in_band.append(index)
        elif in_band and value < address_y - tolerance:
            break
    if in_band:
        return in_band[len(in_band) // 2]
    best: int | None = None
    for index in range(top + 1, end):
        value = path[index]
        if value is None:
            continue
        if best is None or value > (path[best] or value):
            best = index
    return best


def _finish(path: list[float | None], impact: int, end: int, height: int) -> int | None:
    best = impact
    best_y = path[impact]
    impact_y = path[impact]
    if best_y is None or impact_y is None:
        return None
    for index in range(impact + 1, end):
        value = path[index]
        if value is None:
            continue
        if value < best_y:
            best = index
            best_y = value
        if best != impact and value > impact_y - 0.03 * height and index > best:
            break
    if impact_y - best_y < 0.10 * height:
        return None
    return best


def _between(path: list[float | None], start: int, end: int, fraction: float) -> int | None:
    if end <= start + 1:
        return None
    origin = path[start]
    destination = path[end]
    if origin is None or destination is None:
        return None
    target = origin + (destination - origin) * fraction
    best: int | None = None
    best_error: float | None = None
    for index in range(start + 1, end):
        value = path[index]
        if value is None:
            continue
        error = abs(value - target)
        if best_error is None or error < best_error:
            best = index
            best_error = error
    return best


def _cues(
    path: list[float | None],
    address: int | None,
    top: int,
    end: int,
    *,
    height: int,
    fps: float,
) -> list[int] | None:
    if address is None or path[address] is None or top - address < max(2, int(0.15 * fps)):
        return None
    impact = _impact(path, top, end, path[address] or 0, height)
    if impact is None or impact <= top:
        return None
    finish = _finish(path, impact, end, height)
    if finish is None or finish <= impact:
        return None
    raw = [
        address,
        _between(path, address, top, 0.3),
        _between(path, address, top, 0.6),
        top,
        _between(path, top, impact, 0.5),
        impact,
        _between(path, impact, finish, 0.45),
        finish,
    ]
    if any(item is None for item in raw):
        return None
    return _strict([item for item in raw if item is not None], len(path))


def _strict(indexes: list[int], length: int) -> list[int] | None:
    if len(indexes) != len(PHASES):
        return None
    fixed: list[int] = []
    previous = -1
    for index in indexes:
        cursor = max(index, previous + 1)
        if cursor >= length:
            return None
        fixed.append(cursor)
        previous = cursor
    return fixed
