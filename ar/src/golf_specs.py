"""Meter-based gameplay constants and authoritative course scale ownership.

Continuous terrain is authored as ``final physical metres / COURSE_SCALE``
and attached under the existing ``course-scale-root`` exactly once. The ball
alone compensates for that root so its configured diameter remains physical.
"""

COURSE_SCALE = 0.25
COURSE_SCALE_MIN = 0.10
COURSE_SCALE_MAX = 1.00

BALL_DIAMETER_M = 0.022
BALL_RADIUS_M = BALL_DIAMETER_M / 2
BALL_DIAMETER_MIN_M = 0.020
BALL_DIAMETER_MAX_M = 0.043

FAIRWAY_WIDTH_EASY_M = 0.120
FAIRWAY_WIDTH_MEDIUM_M = 0.090
FAIRWAY_WIDTH_HARD_M = 0.065

# Compatibility-only CLI constants. No per-prop art scaling exists.
MINIATURE_STYLE_SCALE = 1.0
DEFAULT_PROP_SCALE = 1.0
MIN_VISIBLE_PROP_XY_M = .018
MAX_BLOCKER_FOOTPRINT_M = .055

# Imported cyberpunk assets are sized per placement by the terrain generator.
TARGETS = {}
DECOR_FOOTPRINTS = {}


def is_prop(asset_id):
    return False
