"""Pinch-grab gesture state machine (pure logic, no hardware).

One recognizer instance tracks ONE hand stream; the application feeds it
the primary hand (hands[0]) or None. All thresholds configurable; every
transition is a pure function of the observation history, so noisy
inputs behave deterministically (see tests/test_gestures.py).

States: idle -> hover -> pinch -> drag -+ (release) -> hover/idle.
  idle:   no hand (or only stale/low-confidence observations)
  hover:  hand present, pinch open
  pinch:  pinch closed but the pointer has not left the dead zone
  drag:   pinch closed and the pointer moved beyond the dead zone

Hysteresis: pinch engages below on_dist (after confirm_frames), and
releases only above off_dist. Confirmation + release hysteresis make
single-frame noise unable to toggle the state.
"""

from __future__ import annotations

import math
import time

IDLE = "idle"
HOVER = "hover"
PINCH = "pinch"
DRAG = "drag"


class GestureConfig:
    def __init__(self, on_dist: float = 0.05, off_dist: float = 0.07,
                 confirm_frames: int = 2, release_frames: int = 1,
                 smooth_alpha: float = 0.45, deadzone: float = 0.004,
                 loss_timeout: float = 0.4, stale_timeout: float = 0.5,
                 min_confidence: float = 0.3) -> None:
        self.on_dist = on_dist
        self.off_dist = off_dist
        self.confirm_frames = confirm_frames
        self.release_frames = release_frames
        self.smooth_alpha = smooth_alpha
        self.deadzone = deadzone
        self.loss_timeout = loss_timeout
        self.stale_timeout = stale_timeout
        self.min_confidence = min_confidence


class GestureState:
    def __init__(self) -> None:
        self.state = IDLE
        self.pos = (0.0, 0.0)       # smoothed normalized pointer
        self.raw_pos = (0.0, 0.0)    # last accepted raw position
        self.just_grabbed = False   # edge: drag/pinch began this update
        self.just_released = False  # edge: active gesture ended this update
        self.active_time = 0.0      # seconds the pinch has been held
        self.confidence = 0.0


class GestureRecognizer:
    def __init__(self, config: GestureConfig | None = None) -> None:
        self.cfg = config or GestureConfig()
        self._state = GestureState()
        self._on_count = 0
        self._off_count = 0
        self._grab_pos: tuple[float, float] | None = None
        self._grab_time = 0.0
        self._last_seen = 0.0

    @property
    def state(self) -> GestureState:
        return self._state

    def reset(self) -> None:
        self._state = GestureState()
        self._on_count = 0
        self._off_count = 0
        self._grab_pos = None

    def update(self, hand, now: float | None = None) -> GestureState:
        """Advance with one observation: a HandState or None."""
        now = time.monotonic() if now is None else now
        st = self._state
        st.just_grabbed = False
        st.just_released = False
        cfg = self.cfg

        usable = (hand is not None
                  and (now - hand.stamp) <= cfg.stale_timeout
                  and hand.confidence >= cfg.min_confidence)
        if usable:
            self._last_seen = now

        if st.state == IDLE:
            if usable:
                st.state = HOVER
                st.pos = hand.pinch_pos
                st.raw_pos = hand.pinch_pos
                st.confidence = hand.confidence
            return st

        # HOVER / PINCH / DRAG require a live hand; otherwise run the
        # loss timer (freeze first, then safe-release -- never jump).
        if not usable:
            if now - self._last_seen >= cfg.loss_timeout:
                if st.state in (PINCH, DRAG):
                    st.just_released = True
                self._reset_active()
                st.state = IDLE
            return st

        # Fresh observation: smooth the pointer, gate motion by deadzone.
        raw = hand.pinch_pos
        st.raw_pos = raw
        st.confidence = hand.confidence
        a = cfg.smooth_alpha
        sm = (st.pos[0] + a * (raw[0] - st.pos[0]),
              st.pos[1] + a * (raw[1] - st.pos[1]))
        if math.hypot(sm[0] - st.pos[0], sm[1] - st.pos[1]) < cfg.deadzone \
                and st.state == DRAG:
            pass  # frozen inside the dead zone while dragging
        else:
            st.pos = sm

        dist = self._pinch_distance(hand)
        if st.state == HOVER:
            if dist is not None and dist < cfg.on_dist:
                self._on_count += 1
                if self._on_count >= cfg.confirm_frames:
                    self._grab(st, now)
            else:
                self._on_count = 0
        else:  # PINCH or DRAG
            st.active_time = now - self._grab_time
            if dist is None or dist > cfg.off_dist:
                self._off_count += 1
                if self._off_count >= cfg.release_frames:
                    st.just_released = True
                    self._reset_active()
                    st.state = HOVER
            else:
                self._off_count = 0
                if st.state == PINCH and self._grab_pos is not None:
                    if math.hypot(st.pos[0] - self._grab_pos[0],
                                   st.pos[1] - self._grab_pos[1]) > cfg.deadzone:
                        st.state = DRAG
        return st

    def _grab(self, st: GestureState, now: float) -> None:
        st.state = PINCH
        st.just_grabbed = True
        self._grab_pos = st.pos
        self._grab_time = now
        st.active_time = 0.0
        self._on_count = 0
        self._off_count = 0

    def _reset_active(self) -> None:
        st = self._state
        if st.state in (PINCH, DRAG):
            st.state = HOVER
        self._on_count = 0
        self._off_count = 0
        self._grab_pos = None

    @staticmethod
    def _pinch_distance(hand):
        try:
            from hand_track import pinch_distance
            return pinch_distance(hand.landmarks)
        except Exception:
            return None
