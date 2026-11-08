"""Hand tracking input layer (MediaPipe Hand Landmarker + simulation).

Camera frames flow: CameraStream --take_frame--> HandTracker.submit_frame
(non-blocking, latest-only mailbox) --> worker thread runs MediaPipe
HandLandmarker (VIDEO mode) --> latest HandState list. The render loop
only ever calls get_hands(), which never blocks and never accumulates
stale frames.

If the native VITURE Linux SDK ever exposes hand joints, that path can
slot in here behind the same HandState interface (as of SDK v2.3.2 it
does not -- headers checked, no hand/finger/palm/landmark API).
"""

from __future__ import annotations

import io
import threading
import time

HAND_LANDMARK_COUNT = 21
THUMB_TIP = 4
INDEX_TIP = 8


class HandState(tuple):
    """(landmarks, handedness, confidence, pinch, pinch_pos, stamp).

    landmarks: 21 (x, y, z) normalized image coords (x right, y DOWN).
    pinch: bool, pinch_pos: (x, y) normalized index-fingertip point.
    stamp: monotonic capture time of the source frame.
    """
    __slots__ = ()

    @property
    def landmarks(self):
        return self[0]

    @property
    def handedness(self):
        return self[1]

    @property
    def confidence(self):
        return self[2]

    @property
    def pinch(self):
        return self[3]

    @property
    def pinch_pos(self):
        return self[4]

    @property
    def stamp(self):
        return self[5]


def pinch_distance(landmarks) -> float:
    """Normalized thumb-tip/index-tip distance (pinch metric)."""
    tx, ty, _tz = landmarks[THUMB_TIP]
    ix, iy, _iz = landmarks[INDEX_TIP]
    dx = tx - ix
    dy = ty - iy
    return (dx * dx + dy * dy) ** 0.5


class HandTracker:
    """MediaPipe hand tracking on a worker thread.

    One HandTracker per process (the landmarker is not thread-safe
    across instances on the same GPU/CPU delegate; a single instance
    with at most two hands is used).
    """

    MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/"
                 "hand_landmarker/hand_landmarker/float16/1/"
                 "hand_landmarker.task")
    MAX_HANDS = 2

    def __init__(self, model_path: str) -> None:
        self._model_path = model_path
        self._lock = threading.Lock()
        self._pending = None  # latest (rgb, w, h, stamp), worker takes it
        self._hands: list = []
        self._frames_seen = 0
        self._frames_done = 0
        self._last_result_stamp = 0.0
        self._inference_ms = 0.0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._landmarker = None

    @property
    def frames_seen(self) -> int:
        with self._lock:
            return self._frames_seen

    @property
    def frames_done(self) -> int:
        with self._lock:
            return self._frames_done

    @property
    def inference_fps(self) -> float:
        with self._lock:
            ms = self._inference_ms
        return 1000.0 / ms if ms > 0 else 0.0

    def start(self) -> None:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        base = mp_python.BaseOptions(model_asset_path=self._model_path)
        options = mp_vision.HandLandmarkerOptions(
            base_options=base,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=self.MAX_HANDS,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5)
        self._landmarker = mp_vision.HandLandmarker.create_from_options(options)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker,
                                        name="hand-tracker", daemon=True)
        self._thread.start()

    def submit_frame(self, jpeg: bytes, width: int, height: int,
                     stamp: float) -> bool:
        """Offer one JPEG frame; False when the worker is still busy
        (the frame is dropped -- latest-only, never queued)."""
        with self._lock:
            if self._pending is not None:
                return False
            self._pending = (jpeg, width, height, stamp)
            self._frames_seen += 1
            return True

    def _worker(self) -> None:
        import time as _time

        import mediapipe as mp
        import numpy as np
        from PIL import Image

        while not self._stop_event.is_set():
            with self._lock:
                job = self._pending
                self._pending = None
            if job is None:
                self._stop_event.wait(0.005)
                continue
            jpeg, width, height, stamp = job
            try:
                img = Image.open(io.BytesIO(jpeg)).convert("RGB")
                if img.size != (width, height):
                    width, height = img.size
                frame = np.asarray(img)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB,
                                    data=frame)
                t0 = _time.monotonic()
                result = self._landmarker.detect_for_video(
                    mp_image, int(stamp * 1000))
                dt_ms = (_time.monotonic() - t0) * 1000.0
                hands = []
                n = len(result.hand_landmarks) if result.hand_landmarks else 0
                for i in range(n):
                    lm = result.hand_landmarks[i]
                    lands = tuple((p.x, p.y, p.z) for p in lm)
                    try:
                        handed = result.handedness[i][0].category_name
                        conf = float(result.handedness[i][0].score)
                    except (IndexError, AttributeError):
                        handed, conf = "Unknown", 0.0
                    ix, iy, _iz = lands[INDEX_TIP]
                    hands.append(HandState(
                        (lands, handed, conf, False, (ix, iy), stamp)))
                with self._lock:
                    self._hands = hands
                    self._frames_done += 1
                    self._last_result_stamp = stamp
                    self._inference_ms = dt_ms
            except Exception:
                continue

    def get_hands(self) -> list:
        """Latest tracked hands (possibly empty). Never blocks."""
        with self._lock:
            return list(self._hands)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        if self._landmarker is not None:
            try:
                self._landmarker.close()
            except Exception:
                pass
            self._landmarker = None


class DesktopHandSimulator:
    """Keyboard/mouse hand simulation (no camera needed).

    Pointer position acts as the index-fingertip; holding G (or the
    left mouse button) pinches. Same HandState interface as HandTracker.
    """

    def __init__(self, win=None) -> None:
        self._win = win
        self._pinch_key = False
        self._pinch_mouse = False

    def start(self) -> None:
        pass

    def set_pinch_key(self, down: bool) -> None:
        self._pinch_key = bool(down)

    def set_pinch_mouse(self, down: bool) -> None:
        self._pinch_mouse = bool(down)

    def get_hands(self) -> list:
        import time as _time

        if self._win is None or not self._win.get_pointer(0):
            return []
        w = max(1, self._win.get_x_size())
        h = max(1, self._win.get_y_size())
        mx = self._win.get_pointer(0).get_x() / w
        my = self._win.get_pointer(0).get_y() / h
        pinch = self._pinch_key or self._pinch_mouse
        # 21 dummy landmarks; index tip tracks the pointer. Resting
        # spread reads OPEN (dist 0.08 > release threshold); pinched
        # thumbs coincide with the index tip (dist 0).
        lands = [(mx, my, 0.0)] * HAND_LANDMARK_COUNT
        lands = list(lands)
        if pinch:
            lands[THUMB_TIP] = (mx, my, 0.0)
        else:
            lands[THUMB_TIP] = (mx + 0.08, my, 0.0)
        lands[INDEX_TIP] = (mx, my, 0.0)
        lands = tuple(lands)
        return [HandState((lands, "Right", 1.0, pinch, (mx, my),
                           _time.monotonic()))]

    def stop(self) -> None:
        pass

    @property
    def frames_seen(self) -> int:
        return 0

    @property
    def frames_done(self) -> int:
        return 0

    @property
    def inference_fps(self) -> float:
        return 0.0
