from app.angles import included_angle, joint_angles, torso_tilt


def test_straight_and_right_elbow():
    assert included_angle((0, 0), (0, 10), (0, 20)) == 180
    assert round(included_angle((0, 0), (0, 10), (10, 10)) or 0, 5) == 90


def test_upright_torso_has_no_tilt():
    joints = [None] * 17
    joints[5] = (40, 10, 1)
    joints[6] = (60, 10, 1)
    joints[11] = (40, 40, 1)
    joints[12] = (60, 40, 1)
    assert torso_tilt(joints) == 0


def test_missing_elbow_stays_empty():
    joints = [None] * 17
    joints[5] = (0, 0, 1)
    joints[7] = (0, 10, 1)
    angles = joint_angles(joints)
    assert angles["leftElbow"] is None
    assert angles["rightElbow"] is None
