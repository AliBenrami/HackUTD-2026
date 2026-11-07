import math

from app.phases import PHASES, segment_swings


def _one_swing() -> list[float]:
    path = [800.0] * 90
    for index in range(10, 31):
        path[index] = 800 - (800 - 200) * (index - 10) / 20
    for index in range(31, 46):
        path[index] = 200 + (820 - 200) * (index - 30) / 15
    for index in range(46, 71):
        path[index] = 820 - (820 - 300) * (index - 45) / 25
    for index in range(71, 90):
        path[index] = 300
    return path


def test_one_swing_marks_the_top_and_keeps_order():
    swings = segment_swings(_one_swing(), height=1000, fps=30)
    assert len(swings) == 1
    cues = swings[0]
    assert len(cues) == len(PHASES)
    assert cues == sorted(cues)
    assert len(set(cues)) == 8
    assert cues[PHASES.index("Top")] == 30
    assert cues[PHASES.index("Address")] < cues[PHASES.index("Top")] < cues[PHASES.index("Impact")]
    assert cues[PHASES.index("Impact")] < cues[PHASES.index("Finish")]


def test_a_held_finish_is_not_a_second_swing():
    swings = segment_swings(_one_swing(), height=1000, fps=30)
    assert len(swings) == 1


def test_two_drops_make_two_swings():
    path = [800.0] * 180
    for start in (10, 100):
        for index in range(start, start + 21):
            path[index] = 800 - (800 - 180) * (index - start) / 20
        for index in range(start + 21, start + 36):
            path[index] = 180 + (820 - 180) * (index - start - 20) / 15
        for index in range(start + 36, start + 55):
            path[index] = 820 - (820 - 400) * (index - start - 35) / 19
    swings = segment_swings(path, height=1000, fps=30)
    assert len(swings) == 2
    assert swings[0][PHASES.index("Top")] < swings[1][PHASES.index("Top")]


def test_a_still_frame_has_no_swing():
    assert segment_swings([500.0] * 60, height=1000, fps=30) == []


def test_finish_stays_on_the_follow_through():
    path = _one_swing()
    for index in range(80, 90):
        path[index] = 300 + (800 - 300) * (index - 80) / 9
    swings = segment_swings(path, height=1000, fps=30)
    finish = swings[0][PHASES.index("Finish")]
    assert 64 <= finish <= 76


def test_setup_at_the_start_is_not_the_swing():
    path = [820.0] * 220
    for index in range(12, 24):
        path[index] = 820 - 80 * math.sin((index - 12) / 11 * math.pi)
    start = 90
    for index in range(start, start + 21):
        path[index] = 820 - (820 - 180) * (index - start) / 20
    for index in range(start + 21, start + 36):
        path[index] = 180 + (840 - 180) * (index - start - 20) / 15
    for index in range(start + 36, start + 61):
        path[index] = 840 - (840 - 280) * (index - start - 35) / 25
    for index in range(start + 61, 220):
        path[index] = 280
    swings = segment_swings(path, height=1000, fps=30)
    assert len(swings) == 1
    cues = swings[0]
    assert cues[PHASES.index("Address")] >= start - 5
    assert cues[PHASES.index("Top")] == start + 20
    assert cues[PHASES.index("Finish")] < start + 70


def test_a_slow_downswing_is_not_cut_off():
    path = [800.0] * 160
    for index in range(10, 31):
        path[index] = 800 - (800 - 200) * (index - 10) / 20
    for index in range(31, 67):
        path[index] = 200 + (820 - 200) * (index - 30) / 36
    for index in range(67, 92):
        path[index] = 820 - (820 - 300) * (index - 66) / 25
    for index in range(92, 160):
        path[index] = 300
    swings = segment_swings(path, height=1000, fps=30)
    assert len(swings) == 1
    assert abs(swings[0][PHASES.index("Top")] - 30) <= 1
    assert swings[0][PHASES.index("Finish")] > swings[0][PHASES.index("Impact")]
