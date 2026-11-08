"""Gesture + pointer + manipulator unit tests (no hardware, no window).

Run:  PYTHONPATH=src uv run python -m unittest discover -s tests -v
"""

import math
import unittest

from gestures import DRAG, HOVER, IDLE, PINCH, GestureRecognizer
from hand_track import HandState


def synth_hand(ix, iy, spread=0.2, conf=0.9, stamp=0.0):
    """Hand with index tip at (ix, iy) and thumb `spread` away."""
    lands = [(ix, iy, 0.0)] * 21
    lands = list(lands)
    lands[8] = (ix, iy, 0.0)
    lands[4] = (ix + spread, iy, 0.0)
    return HandState((tuple(lands), "Right", conf, False, (ix, iy), stamp))


def pinched_hand(ix=0.5, iy=0.5, conf=0.9, stamp=0.0):
    return synth_hand(ix, iy, spread=0.0, conf=conf, stamp=stamp)


class TestPinchHysteresis(unittest.TestCase):
    def test_activation_needs_confirmation(self):
        r = GestureRecognizer()
        t = 0.0
        r.update(synth_hand(0.5, 0.5, spread=0.2, stamp=t), t)
        self.assertEqual(r.state.state, HOVER)
        # One sub-threshold frame is not enough (confirm_frames=2).
        t += 0.05
        r.update(pinched_hand(stamp=t), t)
        self.assertEqual(r.state.state, HOVER)
        t += 0.05
        r.update(pinched_hand(stamp=t), t)
        self.assertEqual(r.state.state, PINCH)
        self.assertTrue(r.state.just_grabbed)

    def test_release_is_deterministic(self):
        r = GestureRecognizer()
        t = 0.0
        r.update(synth_hand(0.5, 0.5, stamp=t), t)
        for _ in range(3):
            t += 0.05
            r.update(pinched_hand(stamp=t), t)
        self.assertIn(r.state.state, (PINCH, DRAG))
        # Open past the release threshold: exactly one release edge.
        t += 0.05
        r.update(synth_hand(0.5, 0.5, spread=0.5, stamp=t), t)
        self.assertTrue(r.state.just_released)
        self.assertEqual(r.state.state, HOVER)
        t += 0.05
        r.update(synth_hand(0.5, 0.5, spread=0.5, stamp=t), t)
        self.assertFalse(r.state.just_released)

    def test_noise_inside_hysteresis_band_does_not_toggle(self):
        r = GestureRecognizer()
        t = 0.0
        r.update(synth_hand(0.5, 0.5, stamp=t), t)
        # Hover near the engage line but above it: never grabs.
        for i in range(10):
            t += 0.05
            r.update(synth_hand(0.5, 0.5, spread=0.051, stamp=t), t)
            self.assertEqual(r.state.state, HOVER)
        # Grab, then hover inside the release band: stays pinched.
        for i in range(3):
            t += 0.05
            r.update(pinched_hand(stamp=t), t)
        self.assertIn(r.state.state, (PINCH, DRAG))
        for i in range(10):
            t += 0.05
            r.update(synth_hand(0.5, 0.5, spread=0.06, stamp=t), t)
            self.assertIn(r.state.state, (PINCH, DRAG))
            self.assertFalse(r.state.just_released)

    def test_drag_after_deadzone(self):
        r = GestureRecognizer()
        t = 0.0
        r.update(synth_hand(0.5, 0.5, stamp=t), t)
        for _ in range(3):
            t += 0.05
            r.update(pinched_hand(0.5, 0.5, stamp=t), t)
        self.assertEqual(r.state.state, PINCH)
        # Move well beyond the dead zone while pinched.
        for i in range(1, 8):
            t += 0.05
            r.update(pinched_hand(0.5 + 0.02 * i, 0.5, stamp=t), t)
        self.assertEqual(r.state.state, DRAG)

    def test_tracking_loss_freezes_then_releases(self):
        r = GestureRecognizer()
        t = 0.0
        r.update(synth_hand(0.5, 0.5, stamp=t), t)
        for _ in range(4):
            t += 0.05
            r.update(pinched_hand(0.6, 0.5, stamp=t), t)
        pos_before = r.state.pos
        # Hand disappears: no jump while frozen inside the loss window.
        for _ in range(3):
            t += 0.05
            r.update(None, t)
            self.assertFalse(r.state.just_released)
        self.assertEqual(r.state.pos, pos_before)
        # Past the loss timeout: safe release, exactly once.
        t += 0.5
        r.update(None, t)
        self.assertTrue(r.state.just_released)
        self.assertEqual(r.state.state, IDLE)
        t += 0.05
        r.update(None, t)
        self.assertFalse(r.state.just_released)

    def test_stale_frames_rejected(self):
        r = GestureRecognizer()
        r.update(synth_hand(0.5, 0.5, stamp=100.0), 100.0)
        # An old observation must not activate or move anything; the
        # recognizer treats it as a dropout (loss timer runs).
        r.update(pinched_hand(stamp=99.7), 100.0)
        self.assertEqual(r.state.state, HOVER)
        self.assertFalse(r.state.just_grabbed)

    def test_low_confidence_rejected_for_activation(self):
        r = GestureRecognizer()
        r.update(synth_hand(0.5, 0.5, stamp=0.0), 0.0)
        r.update(pinched_hand(conf=0.1, stamp=0.05), 0.05)
        r.update(pinched_hand(conf=0.1, stamp=0.10), 0.10)
        self.assertEqual(r.state.state, HOVER)


class TestPointer(unittest.TestCase):
    def test_center_ray_is_forward(self):
        from pointer import ApproxCamera
        cam = ApproxCamera(1920, 1080)
        _o, d = cam.ray_camera_frame(0.5, 0.5)
        self.assertAlmostEqual(d[0], 0.0, places=9)
        self.assertAlmostEqual(d[1], 0.0, places=9)
        self.assertAlmostEqual(d[2], 1.0, places=9)

    def test_corner_rays_are_symmetric(self):
        from pointer import ApproxCamera
        cam = ApproxCamera(1920, 1080)
        _o, a = cam.ray_camera_frame(0.0, 0.0)
        _o, b = cam.ray_camera_frame(1.0, 1.0)
        self.assertAlmostEqual(a[0], -b[0], places=9)
        self.assertAlmostEqual(a[1], -b[1], places=9)

    def test_mirror_flags(self):
        from pointer import ApproxCamera
        a = ApproxCamera(1920, 1080)
        b = ApproxCamera(1920, 1080, flip_x=True)
        _o, da = a.ray_camera_frame(0.25, 0.5)
        _o, db = b.ray_camera_frame(0.25, 0.5)
        self.assertAlmostEqual(da[0], -db[0], places=9)
        self.assertAlmostEqual(da[1], db[1], places=9)

    def test_plane_intersect(self):
        from pointer import intersect_plane
        hit = intersect_plane((0, 0, 0), (0, 0, 1), (0, 0, 5), (0, 0, -1))
        self.assertIsNotNone(hit)
        self.assertAlmostEqual(hit[2], 5.0, places=9)
        # Parallel: no hit. Behind: no hit.
        self.assertIsNone(intersect_plane((0, 0, 0), (1, 0, 0),
                                         (0, 0, 5), (0, 0, -1)))
        self.assertIsNone(intersect_plane((0, 0, 0), (0, 0, -1),
                                         (0, 0, 5), (0, 0, -1)))

    def test_ray_follows_head_yaw(self):
        from pointer import SpatialPointer, ApproxCamera
        from pose_math import quat_rotate
        import math
        ptr = SpatialPointer(ApproxCamera(1920, 1080))
        yaw = math.radians(90.0)
        q = (math.cos(yaw / 2), 0.0, math.sin(yaw / 2), 0.0)
        _o, d = ptr.ray_world(0.5, 0.5, (0, 0, 0), q)
        # Head yawed +90: camera-forward (+Z cam -> -Z GL... ) maps to GL -X.
        self.assertAlmostEqual(d[0], -1.0, places=6)
        self.assertAlmostEqual(d[1], 0.0, places=6)
        self.assertAlmostEqual(d[2], 0.0, places=6)
        # Sanity: identity head looks along GL -Z.
        _o, d0 = ptr.ray_world(0.5, 0.5, (0, 0, 0), (1, 0, 0, 0))
        self.assertAlmostEqual(d0[2], -1.0, places=9)


class FakeGesture:
    def __init__(self, state, pos, grab=False, rel=False):
        self.state = state
        self.pos = pos
        self.just_grabbed = grab
        self.just_released = rel


IDENT_Q = (1.0, 0.0, 0.0, 0.0)
ORIGIN = (0.0, 0.0, 0.0)


class FakePointer:
    def __init__(self, x, y):
        self._x = x
        self._y = y

    def get_x(self):
        return self._x

    def get_y(self):
        return self._y


class FakeWin:
    """Stand-in for a Panda window (pointer only, no display needed)."""

    def __init__(self, w=960, h=540):
        self._w = w
        self._h = h
        self._x = w // 2
        self._y = h // 2

    def move(self, x, y):
        self._x, self._y = x, y

    def get_pointer(self, _i):
        return FakePointer(self._x, self._y)

    def get_x_size(self):
        return self._w

    def get_y_size(self):
        return self._h


class TestDesktopSimPipeline(unittest.TestCase):
    """Mouse -> simulator -> recognizer -> manipulator, no hardware."""

    def setUp(self):
        from panda3d.core import NodePath

        import gestures
        import hand_track
        import manipulate
        import providers

        self.render = NodePath("render")
        self.stage = self.render.attach_new_node("stage")
        self.cube = self.stage.attach_new_node("cube")
        self.cube.set_pos(0, 1.5, 0)
        self.octa = self.stage.attach_new_node("octa")
        self.octa.set_pos(-1.2, 1.8, 0.3)
        self.win = FakeWin()
        self.pose = providers.DesktopPoseProvider(self.win)
        self.sim = hand_track.DesktopHandSimulator(self.win)
        self.recognizer = gestures.GestureRecognizer()
        self.ptr = None
        from pointer import ApproxCamera, SpatialPointer
        self.ptr = SpatialPointer(ApproxCamera(1920, 1080))
        self.man = manipulate.SceneManipulator(
            self.stage, {"cube": self.cube, "octa": self.octa},
            self.render, self.ptr)
        self.man.set_enabled(True)
        # Mirror the app: manipulation suspends mouse-look (the pointer
        # must not swing the view, or drags go backwards).
        self.pose.look_enabled = False

    def _pump(self, now, dt=0.05):
        self.pose.update(dt)
        snap = self.pose.snapshot()
        hands = self.sim.get_hands()
        st = self.recognizer.update(hands[0] if hands else None, now)
        self.man.update(st, snap.pos, snap.quat)
        return st

    def test_hover_selects_center_object(self):
        self.man.set_mode("object")
        self.win.move(480, 270)  # dead centre -> straight ahead
        self._pump(0.0)
        self.assertEqual(self.man.hover_target, "cube")

    def test_full_pinch_drag_release_on_object(self):
        self.man.set_mode("object")
        self.win.move(480, 270)
        t = 0.0
        self._pump(t)  # hover
        self.sim.set_pinch_mouse(True)  # press: pinch closes
        for _ in range(3):
            t += 0.05
            st = self._pump(t)
        self.assertIn(st.state, ("pinch", "drag"))
        self.assertEqual(self.man.grabbed, "cube")
        before = tuple(self.cube.get_pos(self.stage))
        before_octa = tuple(self.octa.get_pos(self.stage))
        # Drag right while pinched.
        self.win.move(580, 270)
        for _ in range(3):
            t += 0.05
            st = self._pump(t)
        self.assertEqual(st.state, "drag")
        self.assertGreater(self.cube.get_x(self.stage), before[0] + 0.02)
        after_octa = tuple(self.octa.get_pos(self.stage))
        for a, b in zip(before_octa, after_octa):
            self.assertAlmostEqual(a, b, places=6)
        # Release: position commits, grab cleared.
        self.sim.set_pinch_mouse(False)
        for _ in range(3):
            t += 0.05
            st = self._pump(t)
        self.assertIsNone(self.man.grabbed)
        self.assertGreater(self.cube.get_x(self.stage), before[0] + 0.02)
        # Undo restores.
        self.assertTrue(self.man.undo())
        for a, b in zip(before, tuple(self.cube.get_pos(self.stage))):
            self.assertAlmostEqual(a, b, places=6)

    def test_stage_drag_moves_everything_together(self):
        self.man.set_mode("stage")
        self.win.move(480, 270)
        t = 0.0
        self._pump(t)
        self.sim.set_pinch_mouse(True)
        for _ in range(3):
            t += 0.05
            self._pump(t)
        self.assertEqual(self.man.grabbed, "stage")
        rel_before = (tuple(self.cube.get_pos(self.stage)),
                      tuple(self.octa.get_pos(self.stage)))
        self.win.move(380, 270)
        for _ in range(3):
            t += 0.05
            self._pump(t)
        self.assertLess(self.stage.get_x(self.render), -0.02)
        rel_after = (tuple(self.cube.get_pos(self.stage)),
                     tuple(self.octa.get_pos(self.stage)))
        for a, b in zip(rel_before[0] + rel_before[1],
                         rel_after[0] + rel_after[1]):
            self.assertAlmostEqual(a, b, places=5)

    def test_look_freeze_while_manipulating(self):
        self.pose.look_enabled = False
        y0, p0 = self.pose._yaw, self.pose._pitch
        self.win.move(100, 100)
        self.pose.update(0.05)
        self.assertEqual(self.pose._yaw, y0)
        self.assertEqual(self.pose._pitch, p0)
        self.pose.look_enabled = True
        self.pose.update(0.05)
        self.assertNotEqual((self.pose._yaw, self.pose._pitch), (y0, p0))


class TestManipulator(unittest.TestCase):
    def setUp(self):
        # NOTE: the manipulator works in the Panda render frame, so the
        # test scene is authored directly in Panda coords (x right,
        # y forward, z up), mirroring the app's gl_space layout:
        #   A cube  straight ahead  -> (0, 1.5, 0)
        #   B octa  front-left      -> (-1.2, 1.8, 0.3)
        from panda3d.core import NodePath
        self.render = NodePath("render")
        self.stage = self.render.attach_new_node("stage")
        self.cube = self.stage.attach_new_node("cube")
        self.cube.set_pos(0, 1.5, 0)
        self.octa = self.stage.attach_new_node("octa")
        self.octa.set_pos(-1.2, 1.8, 0.3)
        from pointer import ApproxCamera, SpatialPointer
        import manipulate
        self.manipulate = manipulate
        self.ptr = SpatialPointer(ApproxCamera(1920, 1080))
        self.man = manipulate.SceneManipulator(
            self.stage, {"cube": self.cube, "octa": self.octa},
            self.render, self.ptr)
        self.man.set_enabled(True)

    def _grab_stage_at_center(self):
        self.man.set_mode("stage")
        g = FakeGesture("pinch", (0.5, 0.5), grab=True)
        self.man.update(g, ORIGIN, IDENT_Q)

    def test_stage_move_preserves_children(self):
        before_cube = tuple(self.cube.get_pos(self.stage))
        before_octa = tuple(self.octa.get_pos(self.stage))
        self.man.reset_stage()
        self._grab_stage_at_center()
        self.assertEqual(self.man.grabbed, "stage")
        # Drag right: pointer (0.6, 0.5).
        g = FakeGesture("drag", (0.6, 0.5))
        self.man.update(g, ORIGIN, IDENT_Q)
        self.man.update(FakeGesture("drag", (0.6, 0.5), rel=True),
                        ORIGIN, IDENT_Q)
        after_cube = tuple(self.cube.get_pos(self.stage))
        after_octa = tuple(self.octa.get_pos(self.stage))
        self.assertGreater(self.stage.get_x(self.render), 0.05)
        for a, b in zip(before_cube, after_cube):
            self.assertAlmostEqual(a, b, places=6)
        for a, b in zip(before_octa, after_octa):
            self.assertAlmostEqual(a, b, places=6)

    def test_object_move_preserves_others(self):
        self.man.set_mode("object")
        self.man.selected = "cube"
        g = FakeGesture("pinch", (0.5, 0.5), grab=True)
        self.man.update(g, ORIGIN, IDENT_Q)
        self.assertEqual(self.man.grabbed, "cube")
        before = tuple(self.octa.get_pos(self.stage))
        g = FakeGesture("drag", (0.6, 0.5))
        self.man.update(g, ORIGIN, IDENT_Q)
        self.man.update(FakeGesture("drag", (0.6, 0.5), rel=True),
                        ORIGIN, IDENT_Q)
        after = tuple(self.octa.get_pos(self.stage))
        for a, b in zip(before, after):
            self.assertAlmostEqual(a, b, places=6)
        self.assertGreater(self.cube.get_x(self.stage), 0.05)

    def test_object_grab_empty_space_ignored(self):
        self.man.set_mode("object")
        self.man.selected = None
        # Point far from any object (top-right corner).
        g = FakeGesture("pinch", (0.95, 0.05), grab=True)
        self.man.update(g, ORIGIN, IDENT_Q)
        self.assertIsNone(self.man.grabbed)

    def test_undo_restores(self):
        self.man.reset_stage()
        self.assertTrue(self.man.undo())
        self.assertAlmostEqual(self.stage.get_x(self.render), 0.0, places=6)
        self.assertFalse(self.man.undo())  # stack empty

    def test_disable_never_modifies(self):
        self._grab_stage_at_center()
        x_before = self.stage.get_x(self.render)
        self.man.set_enabled(False)
        self.assertIsNone(self.man.grabbed)
        self.assertAlmostEqual(self.stage.get_x(self.render), x_before,
                               places=6)
        self.man.set_enabled(True)
        self.assertIsNone(self.man.grabbed)

    def test_disable_mid_drag_restores_grab_start(self):
        self._grab_stage_at_center()
        g = FakeGesture("drag", (0.7, 0.5))
        self.man.update(g, ORIGIN, IDENT_Q)
        moved = self.stage.get_x(self.render)
        self.assertGreater(moved, 0.05)
        self.man.set_enabled(False)  # cancel: back to grab-start pose
        self.assertAlmostEqual(self.stage.get_x(self.render), 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
