"""Head-pose providers: real glasses, desktop simulator, synthetic orbit.

All providers emit GL-frame poses -- position (x right, y up, z backward,
metres) plus Hamilton quaternion (w, x, y, z) -- so the renderer treats
every source identically::

    class PoseProvider:
        name: str
        def start(self) -> None
        def update(self, dt: float) -> None   # advance simulators; viture no-op
        def snapshot(self) -> PoseSnapshot | None
        def recenter(self) -> None
        def stop(self) -> None

PoseSnapshot is immutable-ish (plain tuple payload + monotonic timestamp).
The Viture provider polls the SDK on a DEDICATED background thread and
shares only the latest snapshot under a lock; the render thread never
blocks on USB.
"""

from __future__ import annotations

import math
import sys
import threading
import time

import viture_sdk
from viture_sdk import POSE_STABLE, POSE_UNSTABLE


class PoseSnapshot(tuple):
    """(pos, quat, status, stamp_monotonic, stable)."""
    __slots__ = ()

    @property
    def pos(self):
        return self[0]

    @property
    def quat(self):
        return self[1]

    @property
    def status(self):
        return self[2]

    @property
    def stamp(self):
        return self[3]

    @property
    def stable(self):
        return self[4]

    @property
    def age(self):
        return time.monotonic() - self[3]


def make_snapshot(pos, quat, status):
    return PoseSnapshot((tuple(pos), tuple(quat), int(status),
                         time.monotonic(), status == POSE_STABLE))


class ViturePoseProvider:
    """Carina 6DoF tracking, polled on a background thread."""

    name = "viture"

    def __init__(self, six_dof: bool = True, poll_hz: float = 120.0,
                 request_sbs: bool = False) -> None:
        self._six_dof = six_dof
        self._poll_dt = 1.0 / poll_hz
        self._request_sbs = request_sbs
        self._tracker: viture_sdk.CarinaTracker | None = None
        self._lock = threading.Lock()
        self._snap: PoseSnapshot | None = None
        self._misses = 0
        self._reads = 0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        lib = viture_sdk.load_lib()
        pid = viture_sdk.find_glasses_pid(lib)
        print(f"[pose] glasses product id: 0x{pid:04x}", file=sys.stderr)
        tracker = viture_sdk.CarinaTracker(lib)
        tracker.start(pid, six_dof=self._six_dof)
        if self._request_sbs:
            self._ensure_sbs(tracker)
        self._tracker = tracker
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop,
                                        name="viture-pose", daemon=True)
        self._thread.start()
        print(f"[pose] Carina tracking started "
              f"({'6DoF' if self._six_dof else '3DoF'}) on background thread",
              file=sys.stderr)

    def _poll_loop(self) -> None:
        assert self._tracker is not None
        while not self._stop_event.is_set():
            try:
                read = self._tracker.get_pose(predict=0.0)
            except RuntimeError:
                read = None
            if read is None:
                self._misses += 1
            else:
                pos, quat, status = read
                with self._lock:
                    self._snap = make_snapshot(pos, quat, status)
                self._reads += 1
            self._stop_event.wait(self._poll_dt)

    @staticmethod
    def _ensure_sbs(tracker: viture_sdk.CarinaTracker) -> None:
        """Opt-in: request 3840x1200@90 SBS from the glasses, then verify."""
        want = viture_sdk.DISPLAY_MODE_3840_1200_90HZ_SBS
        try:
            cur = tracker.get_display_mode()
            print(f"[pose] display mode: 0x{cur:02x}", file=sys.stderr)
            if cur == want:
                print("[pose] SBS 3840x1200@90 already active", file=sys.stderr)
                return
            tracker.set_display_mode(want)
            time.sleep(1.0)  # let the output re-enumerate
            cur = tracker.get_display_mode()
            print(f"[pose] display mode now: 0x{cur:02x}", file=sys.stderr)
            if cur != want:
                print("[pose] WARNING: SBS mode not confirmed; "
                      "continuing mono", file=sys.stderr)
        except RuntimeError as exc:
            print(f"[pose] WARNING: display-mode switch failed ({exc}); "
                  "continuing with current mode", file=sys.stderr)

    def update(self, dt: float) -> None:
        pass  # background thread owns polling

    def snapshot(self) -> PoseSnapshot | None:
        with self._lock:
            return self._snap

    def display_mode(self) -> int | None:
        """Glasses display-mode register, or None if unknown."""
        if self._tracker is None:
            return None
        try:
            return self._tracker.get_display_mode()
        except RuntimeError:
            return None

    @property
    def stats(self) -> tuple[int, int]:
        return self._reads, self._misses

    def recenter(self) -> None:
        if self._tracker is None:
            raise RuntimeError("provider not started")
        self._tracker.recenter()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        if self._tracker is not None:
            self._tracker.close()
            self._tracker = None


class DesktopPoseProvider:
    """Mouse-look + keyboard-move simulator (same GL-frame pose output).

    Look direction follows the absolute pointer position inside the
    window (no cursor warping: unreliable under Wayland/XWayland).
    Arrows move on the ground plane, Space/C move up/down.
    R recentres by anchoring the current pointer direction as forward.
    """

    YAW_RANGE = 2.8  # radians across the full window width
    PITCH_RANGE = 1.75  # radians across the full window height

    name = "desktop"

    def __init__(self, win, move_speed: float = 1.2) -> None:
        self._win = win
        self._move_speed = move_speed
        # When False the pointer only aims the hand; the head stays put.
        # The app clears this while manipulation is enabled so pointing
        # at an object does not swing the view away from it.
        self.look_enabled = True
        self._yaw_off = 0.0
        self._pitch_off = 0.0
        self._fixed: tuple[float, float] | None = None
        self._yaw = 0.0
        self._pitch = 0.0
        self._pos = [0.0, 0.0, 0.0]
        self._keys: set[str] = set()
        self._snap: PoseSnapshot | None = None

    def set_fixed(self, yaw_deg: float, pitch_deg: float) -> None:
        """Pin the view (test hook / screenshots); mouse ignored."""
        self._fixed = (math.radians(yaw_deg), math.radians(pitch_deg))

    def start(self) -> None:
        pass

    def key_down(self, key: str) -> None:
        self._keys.add(key)

    def key_up(self, key: str) -> None:
        self._keys.discard(key)

    def _mapped_look(self) -> tuple[float, float]:
        if self._win is not None and self._win.get_pointer(0):
            w = max(1, self._win.get_x_size())
            h = max(1, self._win.get_y_size())
            mx = self._win.get_pointer(0).get_x()
            my = self._win.get_pointer(0).get_y()
            yaw = (mx / w - 0.5) * self.YAW_RANGE - self._yaw_off
            pitch = (0.5 - my / h) * self.PITCH_RANGE - self._pitch_off
            return yaw, max(-1.45, min(1.45, pitch))
        return self._yaw, self._pitch

    def update(self, dt: float) -> None:
        if self._fixed is not None:
            self._yaw, self._pitch = self._fixed
        elif self.look_enabled:
            self._yaw, self._pitch = self._mapped_look()
        # Head-relative ground-plane movement (GL frame).
        sy, cy = math.sin(self._yaw), math.cos(self._yaw)
        fwd = (-sy, 0.0, -cy)
        right = (cy, 0.0, -sy)
        step = self._move_speed * dt
        if "arrow_up" in self._keys:
            self._pos = [a + b * step for a, b in zip(self._pos, fwd)]
        if "arrow_down" in self._keys:
            self._pos = [a - b * step for a, b in zip(self._pos, fwd)]
        if "arrow_left" in self._keys:
            self._pos = [a - b * step for a, b in zip(self._pos, right)]
        if "arrow_right" in self._keys:
            self._pos = [a + b * step for a, b in zip(self._pos, right)]
        if "space" in self._keys:
            self._pos[1] += step
        if "c" in self._keys:
            self._pos[1] -= step
        self._snap = make_snapshot(tuple(self._pos), self._quat(),
                                   POSE_STABLE)

    def _quat(self):
        # q = qyaw * qpitch, GL frame (matches reference orientation math).
        cy, sy = math.cos(self._yaw / 2), math.sin(self._yaw / 2)
        cp, sp = math.cos(self._pitch / 2), math.sin(self._pitch / 2)
        return (cy * cp, cy * sp, sy * cp, -sy * sp)

    def snapshot(self) -> PoseSnapshot | None:
        return self._snap

    def display_mode(self) -> int | None:
        return None

    def recenter(self) -> None:
        # Anchor the current pointer direction as forward.
        yaw, pitch = self._mapped_look()
        self._yaw_off = yaw + self._yaw_off
        self._pitch_off = pitch + self._pitch_off
        self._pos = [0.0, 0.0, 0.0]

    def stop(self) -> None:
        pass


class SinePoseProvider:
    """Deterministic slow orbit (headless smoke tests, screenshots)."""

    name = "synthetic"

    def __init__(self, yaw_amp: float = 0.15,
                 pitch_amp: float = 0.06) -> None:
        self._yaw_amp = yaw_amp
        self._pitch_amp = pitch_amp
        self._t = 0.0
        self._snap: PoseSnapshot | None = None

    def start(self) -> None:
        self._t = 0.0

    def update(self, dt: float) -> None:
        self._t += dt
        yaw = self._yaw_amp * math.sin(0.2 * self._t)
        pitch = self._pitch_amp * math.sin(0.35 * self._t)
        cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
        cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
        quat = (cy * cp, cy * sp, sy * cp, -sy * sp)
        self._snap = make_snapshot((0.0, 0.0, 0.0), quat, POSE_STABLE)

    def snapshot(self) -> PoseSnapshot | None:
        return self._snap

    def display_mode(self) -> int | None:
        return None

    def recenter(self) -> None:
        self._t = 0.0

    def stop(self) -> None:
        pass
