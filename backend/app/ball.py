"""Trace a golf ball after the impact cue.

The detector is Golf Ball Broadcast Model, a YOLOv8 Nano checkpoint trained on
sliced PGA frames. Inference uses overlapping crops of the source frame, then
maps each center back to the full image. A trace is kept only when the ball
leaves the tee. A ball that stays put produces no flight trace, and the trace
stops when the detector loses it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

TILE = 640
OVERLAP = 0.25
TEE_CONFIDENCE = 0.4
FLIGHT_CONFIDENCE = 0.05
MAX_BOX = 40.0
MIN_BOX = 3.0
MAX_GAP = 6
MIN_FLIGHT_SPEED = 18.0
SEARCH_S = 1.2
MODEL_NAME = "golf-ball-broadcast-yolov8n"

_model = None
_device: str | None = None


@dataclass(frozen=True)
class Detection:
    frame: int
    x: float
    y: float
    confidence: float
    size: float


def model_file() -> Path:
    return Path(__file__).resolve().parent.parent / "models" / "golfballyolov8n.pt"


def ball_ready() -> str | None:
    """None when the ball detector can run. Otherwise a short reason it cannot."""
    if not model_file().exists():
        return "The ball model file is missing."
    try:
        import ultralytics  # noqa: F401
    except ImportError:
        return "Install ultralytics."
    return None


def link_flight(by_frame: dict[int, list[Detection]], impact: int, last_frame: int) -> list[Detection]:
    """Follow the ball forward from impact, or return nothing if it stays put."""
    tee = _tee(by_frame, impact)
    if tee is None:
        return []
    trace = [tee]
    missed = 0
    last = tee
    velocity: tuple[float, float] | None = None
    for frame in range(impact + 1, last_frame + 1):
        gap = frame - last.frame
        if velocity is None:
            pred_x, pred_y = last.x, last.y
            gate = 360.0
        else:
            pred_x = last.x + velocity[0] * gap
            pred_y = last.y + velocity[1] * gap
            gate = 70.0 + 45.0 * gap
        chosen = _closest(by_frame.get(frame, []), pred_x, pred_y, gate)
        if chosen is None:
            missed += 1
            if missed > MAX_GAP:
                break
            continue
        step = max(1, frame - last.frame)
        velocity = ((chosen.x - last.x) / step, (chosen.y - last.y) / step)
        trace.append(chosen)
        last = chosen
        missed = 0
    if not _left_the_tee(trace):
        return []
    return trace


def trace_impacts(path: str, impacts: list[int | None], *, fps: float, times: tuple[float, ...] = ()) -> list[list[dict]]:
    """One flight trace per impact frame. Missing flights are empty lists."""
    if ball_ready() is not None or fps <= 0:
        return [[] for _ in impacts]
    windows = [_window(impact, fps) for impact in impacts]
    if not any(windows):
        return [[] for _ in impacts]
    found = _detect_windows(path, windows)
    traces: list[list[dict]] = []
    for impact, window, by_frame in zip(impacts, windows, found, strict=True):
        if impact is None or window is None:
            traces.append([])
            continue
        linked = link_flight(by_frame, impact, window[2])
        traces.append([_sample(item, fps, times) for item in linked])
    return traces


def _window(impact: int | None, fps: float) -> tuple[int, int, int] | None:
    if impact is None or impact < 0:
        return None
    return impact, max(0, impact - 2), impact + max(1, int(SEARCH_S * fps))


def _detect_windows(path: str, windows: list[tuple[int, int, int] | None]) -> list[dict[int, list[Detection]]]:
    import av

    found: list[dict[int, list[Detection]]] = [{} for _ in windows]
    tees: list[Detection | None] = [None for _ in windows]
    last = max(window[2] for window in windows if window is not None)
    container = av.open(path)
    stream = next((item for item in container.streams if item.type == "video"), None)
    if stream is None:
        container.close()
        return found
    model = _load_model()
    try:
        for index, frame in enumerate(container.decode(stream)):
            if index > last:
                break
            image = None
            for swing, window in enumerate(windows):
                if window is None or index < window[1] or index > window[2]:
                    continue
                if image is None:
                    image = frame.to_ndarray(format="bgr24")
                if tees[swing] is None and index >= window[0]:
                    tees[swing] = _tee(found[swing], window[0])
                region = None if tees[swing] is None else _flight_region(tees[swing], image.shape[1], image.shape[0])
                found[swing][index] = _detect(model, image, index, region)
    finally:
        container.close()
    return found


def _flight_region(tee: Detection, width: int, height: int) -> tuple[int, int, int, int]:
    return 0, 0, width, min(height, int(tee.y + 80))


def _detect(model: object, image: object, frame: int, region: tuple[int, int, int, int] | None) -> list[Detection]:
    height, width = image.shape[:2]
    x_min, y_min, x_max, y_max = region or (0, 0, width, height)
    crops = []
    origins = []
    for y0 in _starts(height, TILE):
        for x0 in _starts(width, TILE):
            if x0 + TILE < x_min or x0 > x_max or y0 + TILE < y_min or y0 > y_max:
                continue
            crops.append(image[y0 : y0 + TILE, x0 : x0 + TILE])
            origins.append((x0, y0))
    if not crops:
        return []
    results = model.predict(crops, conf=FLIGHT_CONFIDENCE, verbose=False, imgsz=TILE, device=_torch_device())
    found: list[Detection] = []
    for result, (x0, y0) in zip(results, origins, strict=True):
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            continue
        for box, confidence in zip(boxes.xyxy.tolist(), boxes.conf.tolist(), strict=True):
            x1, y1, x2, y2 = box
            size = max(x2 - x1, y2 - y1)
            if size < MIN_BOX or size > MAX_BOX:
                continue
            found.append(Detection(frame, (x1 + x2) / 2 + x0, (y1 + y2) / 2 + y0, float(confidence), float(size)))
    return _suppress(found)


def _starts(length: int, tile: int) -> list[int]:
    if length <= tile:
        return [0]
    stride = max(1, int(tile * (1 - OVERLAP)))
    starts = list(range(0, length - tile + 1, stride))
    last = length - tile
    if starts[-1] != last:
        starts.append(last)
    return starts


def _suppress(found: list[Detection]) -> list[Detection]:
    kept: list[Detection] = []
    for item in sorted(found, key=lambda det: det.confidence, reverse=True):
        if all(_dist(item, other) > 12 for other in kept):
            kept.append(item)
    return kept


def _tee(by_frame: dict[int, list[Detection]], impact: int) -> Detection | None:
    for frame in (impact, impact - 1, impact + 1, impact - 2, impact + 2):
        candidates = [
            item
            for item in by_frame.get(frame, [])
            if item.confidence >= TEE_CONFIDENCE and MIN_BOX <= item.size <= MAX_BOX
        ]
        if candidates:
            return max(candidates, key=lambda item: item.confidence)
    return None


def _closest(candidates: list[Detection], x: float, y: float, gate: float) -> Detection | None:
    best: Detection | None = None
    best_distance = gate
    for item in candidates:
        if item.confidence < FLIGHT_CONFIDENCE or item.size < MIN_BOX or item.size > MAX_BOX:
            continue
        distance = ((item.x - x) ** 2 + (item.y - y) ** 2) ** 0.5
        if distance <= best_distance:
            best = item
            best_distance = distance
    return best


def _left_the_tee(trace: list[Detection]) -> bool:
    if len(trace) < 3:
        return False
    peak = 0.0
    for previous, nxt in zip(trace, trace[1:]):
        peak = max(peak, _dist(previous, nxt) / max(1, nxt.frame - previous.frame))
    return peak >= MIN_FLIGHT_SPEED and _dist(trace[0], trace[-1]) >= 40


def _dist(a: Detection, b: Detection) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def _sample(item: Detection, fps: float, times: tuple[float, ...]) -> dict:
    time_s = times[item.frame] if item.frame < len(times) else item.frame / fps
    return {
        "frame": item.frame,
        "timeS": round(float(time_s), 4),
        "x": round(item.x, 1),
        "y": round(item.y, 1),
        "confidence": round(item.confidence, 3),
    }


def _load_model():
    global _model
    if _model is None:
        from ultralytics import YOLO

        _model = YOLO(str(model_file()))
    return _model


def _torch_device() -> str:
    global _device
    if _device is None:
        _device = "cpu"
        try:
            import torch

            if torch.backends.mps.is_available():
                _device = "mps"
        except Exception:
            _device = "cpu"
    return _device
