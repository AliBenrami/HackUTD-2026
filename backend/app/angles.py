"""Included joint angles. 180° is straight, matching the swing screen."""

from __future__ import annotations

import math

from app.pose import Joint

Point = tuple[float, float]


def _xy(joint: Joint | None) -> Point | None:
    if joint is None:
        return None
    return (joint[0], joint[1])


def included_angle(a: Point | None, b: Point | None, c: Point | None) -> float | None:
    """Angle at b formed by a-b-c, in degrees."""
    if a is None or b is None or c is None:
        return None
    bax, bay = a[0] - b[0], a[1] - b[1]
    bcx, bcy = c[0] - b[0], c[1] - b[1]
    left = math.hypot(bax, bay)
    right = math.hypot(bcx, bcy)
    if left < 1e-6 or right < 1e-6:
        return None
    cosine = (bax * bcx + bay * bcy) / (left * right)
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def torso_tilt(joints: list[Joint | None]) -> float | None:
    """Degrees the shoulder-hip line leans away from upright. 0 is vertical."""
    left_shoulder = _xy(joints[5]) if len(joints) > 12 else None
    right_shoulder = _xy(joints[6]) if len(joints) > 12 else None
    left_hip = _xy(joints[11]) if len(joints) > 12 else None
    right_hip = _xy(joints[12]) if len(joints) > 12 else None
    if left_shoulder is None or right_shoulder is None or left_hip is None or right_hip is None:
        return None
    shoulder = ((left_shoulder[0] + right_shoulder[0]) / 2, (left_shoulder[1] + right_shoulder[1]) / 2)
    hip = ((left_hip[0] + right_hip[0]) / 2, (left_hip[1] + right_hip[1]) / 2)
    dx = shoulder[0] - hip[0]
    dy = shoulder[1] - hip[1]
    # Image y grows downward, so upright points at (0, -1).
    return abs(math.degrees(math.atan2(dx, -dy)))


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 1)


def joint_angles(joints: list[Joint | None]) -> dict[str, float | None]:
    def at(a: int, b: int, c: int) -> float | None:
        if max(a, b, c) >= len(joints):
            return None
        return included_angle(_xy(joints[a]), _xy(joints[b]), _xy(joints[c]))

    return {
        "leftElbow": _round(at(5, 7, 9)),
        "rightElbow": _round(at(6, 8, 10)),
        "leftKnee": _round(at(11, 13, 15)),
        "rightKnee": _round(at(12, 14, 16)),
        "torsoTilt": _round(torso_tilt(joints)),
    }
