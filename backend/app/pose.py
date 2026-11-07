"""MediaPipe Pose Landmarker, mapped onto the 17 COCO joints the app draws."""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path

# BlazePose indexes for nose, eyes, ears, shoulders, elbows, wrists, hips, knees, ankles.
COCO_FROM_BLAZEPOSE = (0, 2, 5, 7, 8, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28)
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
VISIBILITY_CUTOFF = 0.5

Joint = tuple[float, float, float]


class PoseUnavailable(RuntimeError):
    """The pose runtime or its model file is not available."""


@dataclass(frozen=True)
class PoseVideo:
    fps: float
    width: int
    height: int
    frames: list[list[Joint | None]]
    times: tuple[float, ...] = ()


def model_file() -> Path:
    path = Path(__file__).resolve().parent.parent / "models" / "pose_landmarker_lite.task"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(MODEL_URL, path)
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise PoseUnavailable("The pose model could not be downloaded.") from exc
    return path


def pose_ready() -> str | None:
    """None when pose can run. Otherwise a short reason it cannot."""
    try:
        import av  # noqa: F401
        import mediapipe  # noqa: F401
    except ImportError:
        return "Install mediapipe and av."
    return None


def read_pose(path: str) -> PoseVideo:
    reason = pose_ready()
    if reason is not None:
        raise PoseUnavailable(reason)
    import av
    import mediapipe as mp

    try:
        container = av.open(path)
    except av.FFmpegError as exc:
        raise ValueError("The video could not be opened.") from exc
    stream = next((item for item in container.streams if item.type == "video"), None)
    if stream is None:
        container.close()
        raise ValueError("The video could not be opened.")
    fps = float(stream.average_rate) if stream.average_rate else 30
    if fps <= 1:
        fps = 30
    width = int(stream.codec_context.width or 0)
    height = int(stream.codec_context.height or 0)
    if width <= 0 or height <= 0:
        container.close()
        raise ValueError("The video has no frames.")

    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model_file())),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)
    frames: list[list[Joint | None]] = []
    raw_times: list[float] = []
    last_ms = -1
    index = 0
    try:
        for frame in container.decode(stream):
            rgb = frame.to_ndarray(format="rgb24")
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            pts = frame.time
            raw_times.append(index / fps if pts is None else float(pts))
            timestamp = int(round(raw_times[-1] * 1000))
            if timestamp <= last_ms:
                timestamp = last_ms + 1
            last_ms = timestamp
            frames.append(_coco(landmarker.detect_for_video(image, timestamp), width, height))
            index += 1
    finally:
        container.close()
        landmarker.close()
    if not frames:
        raise ValueError("The video has no frames.")
    return PoseVideo(fps=fps, width=width, height=height, frames=frames, times=_player_times(raw_times, fps))


def _player_times(raw_times: list[float], fps: float) -> tuple[float, ...]:
    """Seconds from the first frame, matching the clock the phone seeks with."""
    if not raw_times:
        return ()
    origin = raw_times[0]
    step = 1 / fps if fps > 0 else 1 / 30
    times: list[float] = []
    last = -step
    for raw in raw_times:
        value = max(0.0, raw - origin)
        if times and value <= last:
            value = last + step
        times.append(value)
        last = value
    return tuple(times)


def _coco(result: object, width: int, height: int) -> list[Joint | None]:
    poses = getattr(result, "pose_landmarks", None) or []
    if not poses:
        return [None] * 17
    landmarks = poses[0]
    joints: list[Joint | None] = []
    for source in COCO_FROM_BLAZEPOSE:
        if source >= len(landmarks):
            joints.append(None)
            continue
        landmark = landmarks[source]
        visibility = landmark.visibility if landmark.visibility is not None else getattr(landmark, "presence", None)
        if visibility is None:
            visibility = 1.0
        x = min(width - 1, max(0.0, float(landmark.x) * width))
        y = min(height - 1, max(0.0, float(landmark.y) * height))
        joints.append((x, y, float(visibility)))
    return joints
