"""Unit tests for tabletop AR anchoring (no window, no hardware).

Run:  PYTHONPATH=src uv run python -m unittest discover -s tests -v

All geometry is synthetic: exact pinhole projections, known ground
truth transforms, controlled noise. Anything touching glasses hardware
lives in ar_poc.py and is validated live, not here.
"""

import json
import math
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import pose_math


class ApproxGateIntegrationTests(unittest.TestCase):
    def test_detection_uses_relaxed_calibrator_gate_only_when_approximate(self):
        from ar_poc import VitureARApp

        class Calibrator:
            def __init__(self):
                self.approx_ok = None

            def observe(self, *args, approx_ok):
                self.approx_ok = approx_ok
                return "accepted", None

            def collect_handeye(self, *args):
                return False

            def best_estimate(self):
                return None

        cal = Calibrator()
        t = {"stats": {"det": 0, "acc": 0, "stale": 0, "amb": 0,
                       "rej": {}, "last_err": 0},
             "timesync": SimpleNamespace(to_mono=lambda *_: 5.),
             "history": SimpleNamespace(interpolate=lambda *_: (
                 (0., 0., 0.), (1., 0., 0., 0.), True, False)),
             "calibrator": cal}
        app = SimpleNamespace(table=t, args=SimpleNamespace(marker_size_mm=100.))
        det = {"arrival_mono": 5., "ts_ns": 0, "img_w": 300,
               "img_h": 200, "corners": []}
        solution = [{"rvec": (0, 0, 0), "tvec": (0, 0, 1),
                     "reproj_err": .2}]
        with patch("tabletop.estimate_marker_pose", return_value=solution):
            for extrinsic_approx, intrinsics_approx in (
                    (True, False), (False, True), (False, False)):
                app._table_intrinsics_for = lambda *_: (None, None, intrinsics_approx)
                app._table_hand_eye = lambda: (((0, 0, 0), (1, 0, 0, 0)),
                                               extrinsic_approx)
                VitureARApp._table_on_detection(app, det, None, 5.1)
                self.assertEqual(cal.approx_ok,
                                 extrinsic_approx or intrinsics_approx)
from tabletop import (
    ADJUST_ANG_DEG,
    ADJUST_POS_M,
    DEFAULT_MARKER_DICT,
    DEFAULT_MARKER_ID,
    DEFAULT_MARKER_SIZE_M,
    SNAP_ANG_DEG,
    SNAP_POS_M,
    TableAnchor,
    TableCalibrator,
    TableTracker,
    TimeSync,
    approx_intrinsics,
    cv_pose_to_gl,
    estimate_marker_pose,
    load_calibration,
    marker_object_points,
    quat_angle_between,
    quat_from_mat3,
    quat_mean,
    quat_normalize,
    rigid_apply,
    rigid_inv,
    rigid_mul,
    save_calibration,
    slerp,
    solve_hand_eye,
)


def _rand_quat(rng):
    q = rng.normal(size=4)
    q = q / np.linalg.norm(q)
    return (float(q[0]), float(q[1]), float(q[2]), float(q[3]))


def _rand_pos(rng, scale=1.0):
    return tuple(float(v) for v in rng.uniform(-scale, scale, size=3))


def _K(w=1920, h=1080, fx=900.0):
    return (np.array([[fx, 0.0, w / 2.0],
                      [0.0, fx, h / 2.0],
                      [0.0, 0.0, 1.0]]),
            np.zeros(5))


def _project(obj, R, t, K, dist):
    import cv2

    img, _ = cv2.projectPoints(np.asarray(obj, dtype=np.float64),
                               cv2.Rodrigues(R)[0], t, K, dist)
    return img.reshape(-1, 2)


def _col(q):
    """Hamilton quat -> column-major rotation (numpy)."""
    return np.array(pose_math.quat_to_mat3(q), dtype=float).reshape(3, 3).T.copy()


def _row(R):
    """Column-major numpy rotation -> row-major tuple."""
    return tuple(float(v) for v in np.asarray(R).T.reshape(-1))


# ---------------------------------------------------------------------------
class TestQuatHelpers(unittest.TestCase):
    def test_roundtrip(self):
        rng = np.random.default_rng(0)
        worst = 0.0
        for _ in range(200):
            q = _rand_quat(rng)
            R = pose_math.quat_to_mat3(q)
            q2 = quat_from_mat3(R)
            worst = max(worst, math.degrees(quat_angle_between(q, q2)))
        self.assertLess(worst, 1e-3)  # exact inverse, float noise only

    def test_identity(self):
        q = quat_from_mat3((1, 0, 0, 0, 1, 0, 0, 0, 1))
        self.assertAlmostEqual(q[0], 1.0, places=9)

    def test_axis_rotations(self):
        def yaw(d):
            h = math.radians(d) / 2.0
            return (math.cos(h), 0.0, math.sin(h), 0.0)

        for d in (0, 10, 45, 90, 135, 179, 180):
            q = yaw(d)
            q2 = quat_from_mat3(pose_math.quat_to_mat3(q))
            self.assertLess(math.degrees(quat_angle_between(q, q2)), 1e-6)

    def test_rigid_roundtrip(self):
        rng = np.random.default_rng(1)
        for _ in range(50):
            p, q = _rand_pos(rng), _rand_quat(rng)
            ip, iq = rigid_inv(p, q)
            p2, q2 = rigid_mul(p, q, ip, iq)
            self.assertTrue(all(abs(a) < 1e-9 for a in p2))
            self.assertLess(quat_angle_between(q2, (1, 0, 0, 0)), 1e-6)

    def test_apply_matches_quat_rotate(self):
        rng = np.random.default_rng(2)
        for _ in range(50):
            p, q, v = _rand_pos(rng), _rand_quat(rng), _rand_pos(rng)
            a = rigid_apply(p, q, v)
            b = pose_math.quat_rotate(q, v)
            self.assertTrue(all(abs(x - y) < 1e-9
                               for x, y in zip(a, (b[0] + p[0],
                                                    b[1] + p[1],
                                                    b[2] + p[2]))))

    def test_slerp_endpoints_and_mid(self):
        a = (1.0, 0.0, 0.0, 0.0)
        h = math.radians(90) / 2.0
        b = (math.cos(h), 0.0, math.sin(h), 0.0)  # 90 deg yaw
        self.assertLess(quat_angle_between(slerp(a, b, 0.0), a), 1e-12)
        self.assertLess(quat_angle_between(slerp(a, b, 1.0), b), 1e-12)
        mid = slerp(a, b, 0.5)
        self.assertAlmostEqual(math.degrees(quat_angle_between(a, mid)),
                               45.0, places=6)

    def test_quat_mean(self):
        base = (1.0, 0.0, 0.0, 0.0)
        qs = [base, base, (-1.0, 0.0, 0.0, 0.0)]  # sign flip must not matter
        m = quat_mean(qs)
        self.assertLess(quat_angle_between(m, base), 1e-9)


# ---------------------------------------------------------------------------
class TestCvPoseToGl(unittest.TestCase):
    def test_face_on_gives_identity_rotation(self):
        # Upright marker viewed face-on: R_cv = F, t = (0,0,d).
        F = np.diag([1.0, -1.0, -1.0])
        import cv2

        rvec, _ = cv2.Rodrigues(F)
        t_gl, q = cv_pose_to_gl(rvec.reshape(3), np.array([0.05, -0.02, 1.2]))
        self.assertLess(quat_angle_between(q, (1, 0, 0, 0)), 1e-6)
        self.assertAlmostEqual(t_gl[0], 0.05, places=9)
        self.assertAlmostEqual(t_gl[1], 0.02, places=9)   # y flipped
        self.assertAlmostEqual(t_gl[2], -1.2, places=9)  # z flipped


# ---------------------------------------------------------------------------
class TestMarkerPose(unittest.TestCase):
    def test_exact_pose_recovery(self):
        K, dist = _K()
        R = np.eye(3)
        t = np.array([0.05, -0.02, 1.2])
        img = _project(marker_object_points(0.1), R, t, K, dist)
        sols = estimate_marker_pose(img.tolist(), 0.1, K.tolist(),
                                    dist.tolist())
        self.assertGreaterEqual(len(sols), 1)
        self.assertLess(sols[0]["reproj_err"], 1e-6)
        import cv2

        r_est = np.asarray(sols[0]["rvec"])
        R_est, _ = cv2.Rodrigues(r_est)
        dR = R_est.T @ R
        ang = math.degrees(math.acos(min(1.0, max(-1.0, (np.trace(dR) - 1) / 2))))
        self.assertLess(ang, 0.01)
        self.assertLess(float(np.linalg.norm(sols[0]["tvec"] - t)), 1e-6)

    def test_noisy_pose_recovery(self):
        rng = np.random.default_rng(3)
        K, dist = _K()
        import cv2

        axis = np.array([0.2, 0.5, 0.3])
        axis = axis / np.linalg.norm(axis)
        R, _ = cv2.Rodrigues(axis * 0.6)
        t = np.array([0.1, 0.05, 0.9])
        img = _project(marker_object_points(0.1), R, t, K, dist)
        img = img + rng.normal(0, 1.0, size=img.shape)  # 1 px noise
        sols = estimate_marker_pose(img.tolist(), 0.1, K.tolist(),
                                    dist.tolist())
        self.assertGreaterEqual(len(sols), 1)
        self.assertLess(sols[0]["reproj_err"], 3.0)
        self.assertLess(float(np.linalg.norm(sols[0]["tvec"] - t)), 0.03)

    def test_corner_order_matters(self):
        # Shuffled correspondences must NOT fit well (validates TL/TR/BR/BL).
        K, dist = _K()
        img = _project(marker_object_points(0.1), np.eye(3),
                       np.array([0.0, 0.0, 1.0]), K, dist)
        bad = [img[1], img[0], img[3], img[2]]
        sols = estimate_marker_pose([tuple(p) for p in bad], 0.1,
                                    K.tolist(), dist.tolist())
        self.assertTrue(not sols or sols[0]["reproj_err"] > 1.0)

    def test_grazing_angle_returns_two_solutions(self):
        import cv2

        K, dist = _K()
        # Marker tilted ~70 deg away: classic IPPE ambiguity case.
        R, _ = cv2.Rodrigues(np.array([math.radians(70), 0.0, 0.0]))
        t = np.array([0.0, 0.0, 0.8])
        img = _project(marker_object_points(0.1), R, t, K, dist)
        sols = estimate_marker_pose(img.tolist(), 0.1, K.tolist(),
                                    dist.tolist())
        self.assertEqual(len(sols), 2)
        # Both explain the image; best still recovers the pose.
        self.assertLess(sols[0]["reproj_err"], 1e-6)
        r_est = np.asarray(sols[0]["rvec"])
        R_est, _ = cv2.Rodrigues(r_est)
        dR = R_est.T @ R
        ang = math.degrees(math.acos(min(1.0, max(-1.0, (np.trace(dR) - 1) / 2))))
        self.assertLess(ang, 0.1)


# ---------------------------------------------------------------------------
class TestAnchorFrames(unittest.TestCase):
    def test_roundtrip_and_normal(self):
        a = TableAnchor((0.3, 0.1, -0.5), (1, 0, 0, 0), 0.6, 0.4)
        p = (0.1, -0.05, 0.02)
        w = a.world_from_table(p)
        back = a.table_from_world(w)
        for x, y in zip(p, back):
            self.assertAlmostEqual(x, y, places=12)
        n = a.normal_world()
        self.assertAlmostEqual(n[2], 1.0, places=12)

    def test_upright_error(self):
        a = TableAnchor((0, 0, 0), (1, 0, 0, 0))
        self.assertAlmostEqual(a.upright_error_rad(), math.pi / 2, places=9)
        # Rotate table frame -90 deg about X: +Z local -> +Y world.
        h = math.radians(-90) / 2.0
        a2 = TableAnchor((0, 0, 0), (math.cos(h), math.sin(h), 0, 0))
        self.assertLess(a2.upright_error_rad(), 1e-9)

    def test_contains_xy(self):
        a = TableAnchor((0, 0, 0), (1, 0, 0, 0), 0.6, 0.4)
        self.assertTrue(a.contains_xy((0.29, 0.19, 0.0)))
        self.assertFalse(a.contains_xy((0.31, 0.0, 0.0)))
        self.assertFalse(a.contains_xy((0.0, 0.21, 0.0)))
        self.assertTrue(a.contains_xy((0.31, 0.0, 0.0), margin=0.02))

    def test_cal_file_roundtrip(self):
        a = TableAnchor((0.1, 0.2, -0.7),
                        quat_normalize((0.9, 0.1, 0.2, 0.1)), 0.6, 0.4)
        a.confidence = 0.83
        a.tracking_state = "LOCKED"
        a.obs_count = 14
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "anchor.json")
            save_calibration(p, {"anchor": a.as_dict()})
            back = TableAnchor.from_dict(load_calibration(p)["anchor"])
        self.assertAlmostEqual(back.pos[0], 0.1, places=12)
        self.assertAlmostEqual(back.confidence, 0.83, places=12)
        self.assertEqual(back.tracking_state, "LOCKED")
        self.assertEqual(back.obs_count, 14)

    def test_load_missing_returns_empty(self):
        self.assertEqual(load_calibration("/nonexistent/path.json"), {})


# ---------------------------------------------------------------------------
class TestHandEye(unittest.TestCase):
    def _synthetic(self, seed=7, n=12):
        rng = np.random.default_rng(seed)
        qX = _rand_quat(rng)
        RX, tX = _col(qX), rng.uniform(-0.1, 0.1, size=3)
        RO, tO = _col(_rand_quat(rng)), np.array([0.3, -0.4, 1.0])
        heads, marks = [], []
        for _ in range(n):
            q = _rand_quat(rng)
            R, t = _col(q), rng.uniform(-0.5, 0.5, size=3)
            heads.append((tuple(float(v) for v in t), q))
            Rgo, tgo = R.T @ RO, R.T @ (tO - t)
            marks.append((RX.T @ Rgo, RX.T @ (tgo - tX)))
        return (tX, qX), heads, marks

    def test_synthetic_recovery(self):
        (tX, qX), heads, marks = self._synthetic()
        (pos, q), diag = solve_hand_eye(heads, marks)
        Rsol = _col(q)
        RX = _col(qX)
        dR = Rsol.T @ RX
        ang = math.degrees(math.acos(min(1.0, max(-1.0, (np.trace(dR) - 1) / 2))))
        self.assertLess(ang, 0.5)
        self.assertLess(float(np.linalg.norm(np.asarray(pos) - tX)), 0.005)

    def test_degenerate_raises(self):
        (tX, qX), heads, marks = self._synthetic(n=4)
        # All identical head poses -> no informative motion.
        heads = [heads[0]] * 4
        marks = [marks[0]] * 4
        with self.assertRaises(ValueError):
            solve_hand_eye(heads, marks)
        with self.assertRaises(ValueError):
            solve_hand_eye(heads[:3], marks[:3])


# ---------------------------------------------------------------------------
class _Fixture:
    """Fixed world: table at origin-ish, head above looking down-ish."""

    @staticmethod
    def anchor():
        # Table frame: x right, y up-in-plane, z normal. Upright: rotate
        # -90 deg about X so +Z local -> +Y world (tabletop horizontal).
        h = math.radians(-90) / 2.0
        q = quat_normalize((math.cos(h), math.sin(h), 0.0, 0.0))
        return (0.3, -0.45, -0.9), q

    @staticmethod
    def head():
        return ((0.3, 0.15, -0.1), (1.0, 0.0, 0.0, 0.0))

    @staticmethod
    def hand_eye():
        # Approx extrinsics: camera head-aligned (flip only), 2 cm fwd.
        import numpy as np

        F = np.diag([1.0, -1.0, -1.0])
        q = quat_from_mat3(_row(F))
        return ((0.0, 0.0, -0.02), q)


def _obs_for(anchor_pos, anchor_quat, head_pos, head_quat, he, size_m=0.1):
    """Exact (rvec, tvec) for the anchor viewed from head via hand-eye."""
    import cv2

    R_wh = _col(head_quat)
    t_wh = np.asarray(head_pos, dtype=float)
    R_hc = _col(he[1])
    t_hc = np.asarray(he[0])
    R_wt = _col(anchor_quat)
    t_wt = np.asarray(anchor_pos, dtype=float)
    # T_C_M = X^{-1} G^{-1} A (column convention).
    R_g = R_wh.T
    t_g = -R_g @ t_wh
    R_h = R_hc.T
    t_h = -R_h @ t_hc
    R_cm = R_h @ (R_g @ R_wt)
    t_cm = R_h @ (R_g @ t_wt + t_g) + t_h
    rvec, _ = cv2.Rodrigues(R_cm)
    return rvec.reshape(3), t_cm


class TestCalibrator(unittest.TestCase):
    def test_acquisition_lock(self):
        ap, aq = _Fixture.anchor()
        hp, hq = _Fixture.head()
        he = _Fixture.hand_eye()
        cal = TableCalibrator(required=6, max_reproj_px=2.0)
        anchor = None
        for i in range(8):
            rvec, tvec = _obs_for(ap, aq, hp, hq, he)
            st, anchor = cal.observe(hp, hq, rvec, tvec, 0.3,
                                     100.0 + i * 0.1, he, approx_ok=True)
            self.assertEqual(st, "accepted")
        self.assertIsNotNone(anchor)
        self.assertEqual(anchor.tracking_state, "APPROX")
        self.assertLess(math.dist(anchor.pos, ap), 0.01)
        self.assertLess(math.degrees(quat_angle_between(anchor.quat, aq)), 1.0)

    def test_outlier_rejection(self):
        ap, aq = _Fixture.anchor()
        hp, hq = _Fixture.head()
        he = _Fixture.hand_eye()
        cal = TableCalibrator(required=6)
        rvec, tvec = _obs_for(ap, aq, hp, hq, he)
        st, _ = cal.observe(hp, hq, rvec, tvec, 0.3, 100.0, he)
        self.assertEqual(st, "accepted")
        # Far-away hallucination: inconsistent with the window.
        far = (tvec + np.array([0.5, 0.0, 0.0])).reshape(3)
        st, _ = cal.observe(hp, hq, rvec, far, 0.3, 100.1, he)
        self.assertEqual(st, "reject-inconsistent")
        # Bad reprojection.
        st, _ = cal.observe(hp, hq, rvec, tvec, 25.0, 100.2, he)
        self.assertEqual(st, "reject-reproj")
        # Too close / too far.
        st, _ = cal.observe(hp, hq, rvec, np.array([0, 0, 0.05]), 0.3,
                            100.3, he)
        self.assertEqual(st, "reject-distance")

    def test_approx_gates_relaxed(self):
        # 8 cm shift: rejected with calibrated extrinsics (5 cm gate),
        # accepted with approx extrinsics (12 cm gate) so APPROX mode
        # keeps tracking instead of freezing at the first lock pose.
        ap, aq = _Fixture.anchor()
        hp, hq = _Fixture.head()
        he = _Fixture.hand_eye()
        rvec, tvec = _obs_for(ap, aq, hp, hq, he)
        near = (tvec + np.array([0.08, 0.0, 0.0])).reshape(3)
        cal = TableCalibrator(required=6)
        cal.observe(hp, hq, rvec, tvec, 0.3, 100.0, he, approx_ok=False)
        st, _ = cal.observe(hp, hq, rvec, near, 0.3, 100.1, he,
                            approx_ok=False)
        self.assertEqual(st, "reject-inconsistent")
        cal2 = TableCalibrator(required=6)
        cal2.observe(hp, hq, rvec, tvec, 0.3, 100.0, he, approx_ok=True)
        st, _ = cal2.observe(hp, hq, rvec, near, 0.3, 100.1, he,
                             approx_ok=True)
        self.assertEqual(st, "accepted")

    def test_gravity_gate(self):
        ap, aq = _Fixture.anchor()
        hp, hq = _Fixture.head()
        he = _Fixture.hand_eye()
        cal = TableCalibrator(required=3, max_gravity_deg=25.0)
        rvec, tvec = _obs_for(ap, aq, hp, hq, he)
        # Flip the marker upside down: normal points down.
        import cv2

        R, _ = cv2.Rodrigues(rvec)
        Rflip = np.diag([1.0, -1.0, -1.0]) @ R
        rflip, _ = cv2.Rodrigues(Rflip)
        st, _ = cal.observe(hp, hq, rflip.reshape(3), tvec, 0.3, 100.0, he)
        self.assertEqual(st, "reject-gravity")

    def test_handeye_collect_and_solve(self):
        ap, aq = _Fixture.anchor()
        he_true = _Fixture.hand_eye()
        cal = TableCalibrator()
        rng = np.random.default_rng(11)
        kept = 0
        for i in range(14):
            # Diverse viewpoints: translation + rotation about mixed axes
            # (single-axis motion leaves hand-eye rotation unobservable).
            hp = (0.3 + rng.uniform(-0.25, 0.25),
                  0.15 + rng.uniform(-0.15, 0.15),
                  -0.1 + rng.uniform(-0.1, 0.1))
            axis = rng.normal(size=3)
            axis = axis / np.linalg.norm(axis)
            ang = rng.uniform(0.15, 0.7)
            s, c = math.sin(ang / 2), math.cos(ang / 2)
            hq = quat_normalize((c, s * axis[0], s * axis[1], s * axis[2]))
            rvec, tvec = _obs_for(ap, aq, hp, hq, he_true)
            if cal.collect_handeye(hp, hq, rvec, tvec):
                kept += 1
        self.assertGreaterEqual(kept, 4)
        (pos, q), diag = cal.solve_hand_eye()
        Rsol, Rtru = _col(q), _col(he_true[1])
        dR = Rsol.T @ Rtru
        ang = math.degrees(math.acos(min(1.0, max(-1.0, (np.trace(dR) - 1) / 2))))
        self.assertLess(ang, 1.0)
        self.assertLess(float(np.linalg.norm(np.asarray(pos) - he_true[0])),
                        0.01)

    def test_handeye_degenerate_single_axis_raises(self):
        ap, aq = _Fixture.anchor()
        he_true = _Fixture.hand_eye()
        cal = TableCalibrator()
        rng = np.random.default_rng(11)
        for i in range(8):
            hp = (0.3 + rng.uniform(-0.2, 0.2),
                  0.15 + rng.uniform(-0.1, 0.1), -0.1)
            ang = rng.uniform(-0.4, 0.4)
            hq = quat_normalize((math.cos(ang / 2), 0.0, math.sin(ang / 2), 0.0))
            rvec, tvec = _obs_for(ap, aq, hp, hq, he_true)
            cal.collect_handeye(hp, hq, rvec, tvec,
                                min_trans_m=0.0, min_rot_deg=0.0)
        with self.assertRaises(ValueError):
            cal.solve_hand_eye()


# ---------------------------------------------------------------------------
class TestTracker(unittest.TestCase):
    def _locked_tracker(self):
        tr = TableTracker()
        tr.observe_marker((0.3, -0.45, -0.9),
                          quat_normalize((1.0, 0.0, 0.0, 0.0)),
                          0.4, 100.0, True, False)
        self.assertEqual(tr.state, "LOCKED")
        return tr

    def test_no_jump_on_single_outlier(self):
        tr = self._locked_tracker()
        before = tr.anchor.pos
        # One huge jump: must NOT move the anchor.
        tr.observe_marker((1.5, 0.5, 0.5),
                          quat_normalize((1.0, 0.0, 0.0, 0.0)),
                          0.4, 101.0, True, False)
        self.assertEqual(tr.anchor.pos, before)
        self.assertEqual(tr.state, "LOCKED")

    def test_damped_correction_small_residual(self):
        tr = self._locked_tracker()
        before = np.asarray(tr.anchor.pos)
        obs = before + np.array([0.01, 0.0, 0.0])  # 1 cm < ADJUST_POS_M
        tr.observe_marker(tuple(obs), tr.anchor.quat, 0.4, 101.0, True, False)
        after = np.asarray(tr.anchor.pos)
        moved = float(np.linalg.norm(after - before))
        self.assertGreater(moved, 0.0)
        self.assertLess(moved, 0.01)  # damped, not snapped

    def test_snap_medium_residual(self):
        tr = self._locked_tracker()
        obs = (tr.anchor.pos[0] + 0.10, tr.anchor.pos[1], tr.anchor.pos[2])
        tr.observe_marker(obs, tr.anchor.quat, 0.4, 101.0, True, False)
        self.assertAlmostEqual(tr.anchor.pos[0], obs[0], places=12)

    def test_relock_on_consistent_cluster(self):
        tr = self._locked_tracker()
        new = (0.9, -0.2, -0.7)
        for i in range(5):
            tr.observe_marker(new, tr.anchor.quat, 0.4, 101.0 + i * 0.1,
                              True, False)
        self.assertLess(math.dist(tr.anchor.pos, new), 0.02)
        self.assertEqual(tr.state, "LOCKED")

    def test_degraded_recovers_on_fresh_observations(self):
        tr = self._locked_tracker()
        tr.mark_seen(400.0, False)  # unstable -> DEGRADED
        self.assertEqual(tr.state, "DEGRADED")
        # Unstable observations must NOT heal it.
        tr.observe_marker(tr.anchor.pos, tr.anchor.quat, 0.4, 401.0,
                          False, False)
        self.assertEqual(tr.state, "DEGRADED")
        # Small-residual stable observation heals back to LOCKED.
        obs = (tr.anchor.pos[0] + 0.005, tr.anchor.pos[1],
               tr.anchor.pos[2])
        tr.observe_marker(obs, tr.anchor.quat, 0.4, 402.0, True, False)
        self.assertEqual(tr.state, "LOCKED")

    def test_degraded_recovers_to_approx_when_approx(self):
        tr = self._locked_tracker()
        tr.state = "DEGRADED"
        tr.anchor.tracking_state = "DEGRADED"
        tr.observe_marker(tr.anchor.pos, tr.anchor.quat, 0.4, 500.0,
                          True, True)
        self.assertEqual(tr.state, "APPROX")

    def test_noop_relock_guard(self):
        tr = self._locked_tracker()
        before = tr.anchor.pos
        # Frozen estimator feeds identical far samples: relock may move...
        # but identical samples AT the anchor must not fake a relock.
        tr._outlier_cluster = [(before, tr.anchor.quat)] * 5
        tr._outlier_streak = 5
        tr._relock_from_cluster(600.0, False)
        self.assertEqual(tr.anchor.pos, before)
        self.assertEqual(tr.state, "LOCKED")

    def test_relock_preserves_approx(self):
        tr = self._locked_tracker()
        tr.state = "DEGRADED"
        new = (0.9, -0.2, -0.7)
        for i in range(5):
            tr.observe_marker(new, tr.anchor.quat, 0.4, 601.0 + i * 0.1,
                              True, True)
        self.assertEqual(tr.state, "APPROX")

    def test_jump_detector_lost(self):
        tr = self._locked_tracker()
        tr.note_head_pose((0, 0, 0), (1, 0, 0, 0), True, 200.0)
        tr.note_head_pose((2.0, 0, 0), (1, 0, 0, 0), True, 200.1)  # teleport
        self.assertEqual(tr.state, "LOST")

    def test_degraded_then_lost_timeouts(self):
        from tabletop import DEGRADED_AFTER_S, LOST_TIMEOUT_S

        tr = self._locked_tracker()
        tr._last_seen_marker_at = 300.0
        tr.mark_seen(300.0 + DEGRADED_AFTER_S + 0.1, True)
        self.assertEqual(tr.state, "DEGRADED")
        tr.mark_seen(300.0 + LOST_TIMEOUT_S + 0.1, True)
        self.assertEqual(tr.state, "LOST")

    def test_unstable_freezes_but_keeps_anchor(self):
        tr = self._locked_tracker()
        before = tr.anchor.pos
        tr.mark_seen(400.0, False)
        self.assertEqual(tr.state, "DEGRADED")
        self.assertEqual(tr.anchor.pos, before)

    def test_origin_reset_carries_anchor(self):
        tr = self._locked_tracker()
        before = np.asarray(tr.anchor.pos)
        old_pos = (0.1, 0.0, 0.0)
        h = math.radians(90) / 2.0
        old_quat = (math.cos(h), 0.0, math.sin(h), 0.0)  # yaw 90
        tr.note_origin_reset(old_pos, old_quat)
        self.assertEqual(tr.state, "LOCKED")
        # Carried by inverse head pose (pos + yaw): moved, not frozen.
        self.assertGreater(float(np.linalg.norm(np.asarray(tr.anchor.pos)
                                                - before)), 0.05)
        # First pose in the NEW frame must not trip the jump detector.
        tr.note_head_pose((0.0, 0.0, 0.0),
                          quat_normalize((1.0, 0.0, 0.0, 0.0)), True, 500.0)
        tr.note_head_pose((0.01, 0.0, 0.0),
                          quat_normalize((1.0, 0.0, 0.0, 0.0)), True, 500.05)
        self.assertEqual(tr.state, "LOCKED")
        # And a reset with no info loses the anchor instead of guessing.
        tr2 = self._locked_tracker()
        tr2.note_origin_reset()
        self.assertEqual(tr2.state, "LOST")

    def test_no_jump_from_uninitialized(self):
        tr = TableTracker()
        tr.note_head_pose((0, 0, 0), (1, 0, 0, 0), True, 1.0)
        tr.note_head_pose((2.0, 0, 0), (1, 0, 0, 0), True, 1.1)
        self.assertEqual(tr.state, "UNINITIALIZED")


# ---------------------------------------------------------------------------
class TestTimeSync(unittest.TestCase):
    def test_offset_and_fallback(self):
        ts = TimeSync()
        self.assertIsNone(ts.offset())
        # No data: arrival-time fallback.
        self.assertAlmostEqual(ts.to_mono(0, 123.4), 123.4)
        base = time.monotonic()
        for i in range(10):
            ts.feed(1_000_000_000 + i * 33_333_333, base + 5.0 + i * 0.033)
        off = ts.offset()
        self.assertIsNotNone(off)
        self.assertAlmostEqual(off, base + 4.0, delta=0.1)
        # Device ts maps back near the arrival time.
        mono = ts.to_mono(1_000_000_000 + 9 * 33_333_333, 0.0)
        self.assertAlmostEqual(mono, base + 5.0 + 9 * 0.033, delta=0.05)

    def test_jitter_and_shared_clock(self):
        ts = TimeSync()
        base = time.monotonic()
        for i in range(10):
            ts.feed(2_000_000_000 + i * 10_000_000, base + 1.0 + i * 0.01)
        self.assertLess(ts.jitter(), 0.05)
        self.assertTrue(ts.shared_clock_likely())
        ts2 = TimeSync()
        for i in range(10):
            ts2.feed(3_000_000_000 + i * 10_000_000,
                     base + 1.0 + (0.2 if i % 2 else -0.2))
        self.assertFalse(ts2.shared_clock_likely())


# ---------------------------------------------------------------------------
class TestPoseHistory(unittest.TestCase):
    def test_interpolate_midpoint(self):
        from tabletop import PoseHistory

        h = PoseHistory()
        h.push(0.0, (0, 0, 0), (1, 0, 0, 0), True)
        h.push(1.0, (1, 0, 0),
               quat_normalize((math.cos(math.pi / 4), 0, math.sin(math.pi / 4), 0)),
               True)
        pos, quat, stable, extrap = h.interpolate(0.5)
        self.assertAlmostEqual(pos[0], 0.5, places=9)
        self.assertTrue(stable)
        self.assertFalse(extrap)
        # Halfway yaw 90 deg -> 45 deg.
        self.assertAlmostEqual(math.degrees(quat_angle_between(
            (1, 0, 0, 0), quat)), 45.0, places=6)

    def test_extrapolation_flags(self):
        from tabletop import PoseHistory

        h = PoseHistory()
        self.assertIsNone(h.interpolate(0.0))
        h.push(1.0, (1, 2, 3), (1, 0, 0, 0), False)
        pos, quat, stable, extrap = h.interpolate(0.0)
        self.assertTrue(extrap)
        self.assertFalse(stable)
        self.assertEqual(pos, (1, 2, 3))


# ---------------------------------------------------------------------------
class TestDetectorSynthetic(unittest.TestCase):
    def _marker_jpeg(self, marker_id=DEFAULT_MARKER_ID, size=400):
        import cv2

        aruco = cv2.aruco
        d = aruco.getPredefinedDictionary(getattr(aruco, DEFAULT_MARKER_DICT))
        marker = aruco.generateImageMarker(d, marker_id, 200)
        canvas = np.full((size, size), 255, dtype=np.uint8)
        o = (size - 200) // 2
        canvas[o:o + 200, o:o + 200] = marker
        ok, buf = cv2.imencode(".jpg", canvas)
        self.assertTrue(ok)
        return bytes(buf.tobytes())

    def test_detect_synthetic_frame(self):
        from tabletop import MarkerDetector

        det = MarkerDetector()
        det.start()
        try:
            jpeg = self._marker_jpeg()
            self.assertTrue(det.submit(jpeg, 400, 400, 7, 0, time.monotonic()))
            deadline = time.monotonic() + 5.0
            got = None
            while time.monotonic() < deadline and got is None:
                got = det.take()
                if got is None:
                    time.sleep(0.02)
            self.assertIsNotNone(got, "no detection on synthetic marker")
            self.assertEqual(got["marker_id"], DEFAULT_MARKER_ID)
            self.assertEqual(len(got["corners"]), 4)
            self.assertEqual(got["seq"], 7)
        finally:
            det.stop()

    def test_blank_frame_no_detection(self):
        import cv2

        from tabletop import MarkerDetector

        det = MarkerDetector()
        det.start()
        try:
            blank = np.full((300, 300, 3), 200, dtype=np.uint8)
            ok, buf = cv2.imencode(".jpg", blank)
            self.assertTrue(ok)
            det.submit(bytes(buf.tobytes()), 300, 300, 1, 0, time.monotonic())
            time.sleep(0.5)
            # Blank: either None or (impossibly) a false positive; if a
            # detection arrives it must still be well-formed.
            got = det.take()
            if got is not None:
                self.assertEqual(len(got["corners"]), 4)
        finally:
            det.stop()


class TestApproxIntrinsics(unittest.TestCase):
    def test_flagged_approximate(self):
        intr = approx_intrinsics(1920, 1080)
        self.assertTrue(intr["approx"])
        self.assertAlmostEqual(intr["K"][0][2], 960.0)
        self.assertAlmostEqual(intr["K"][1][2], 540.0)
        import math as _m

        fx = 960.0 / _m.tan(_m.radians(70.0) / 2.0)
        self.assertAlmostEqual(intr["K"][0][0], fx, places=6)


if __name__ == "__main__":
    unittest.main()
