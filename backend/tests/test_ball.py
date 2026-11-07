from app.ball import Detection, link_flight


def _det(frame: int, x: float, y: float, confidence: float = 0.8, size: float = 20) -> Detection:
    return Detection(frame, x, y, confidence, size)


def test_a_ball_that_stays_put_has_no_flight_trace():
    by_frame = {
        frame: [_det(frame, 860 - (frame - 114) * 0.5, 1560 - (frame - 114) * 0.4)]
        for frame in range(112, 150)
    }
    assert link_flight(by_frame, 114, 149) == []


def test_flight_follows_the_ball_and_stops_when_detections_end():
    points = {
        429: (733.0, 1670.1, 0.866, 23.9),
        430: (671.4, 1433.5, 0.806, 16.1),
        431: (627.2, 1272.7, 0.826, 11.9),
        432: (601.2, 1173.3, 0.848, 9.5),
        433: (583.3, 1106.6, 0.656, 8.7),
        439: (539.2, 941.4, 0.306, 6.2),
        440: (535.1, 929.6, 0.136, 7.1),
        441: (532.5, 918.7, 0.300, 5.8),
        442: (529.9, 910.0, 0.084, 6.0),
        443: (526.9, 902.8, 0.059, 7.1),
        445: (524.5, 891.7, 0.160, 4.7),
        446: (28.8, 425.8, 0.089, 4.9),
        447: (521.7, 883.5, 0.123, 5.9),
    }
    by_frame = {frame: [_det(frame, x, y, confidence, size)] for frame, (x, y, confidence, size) in points.items()}
    by_frame[445].append(_det(445, 27.3, 427.1, 0.051, 4.8))
    trace = link_flight(by_frame, 429, 461)
    assert [item.frame for item in trace][0] == 429
    assert trace[-1].frame == 447
    assert all(item.x > 500 for item in trace)
    assert trace[-1].y < trace[0].y
