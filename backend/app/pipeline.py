"""Turn a swing video into the frame track and phase cues the phone already draws.

Pose comes from MediaPipe. Phases come from the hand path. Shaft and club-head
boxes stay empty until a club detector is added beside `hands_box`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.angles import joint_angles
from app.ball import MODEL_NAME, ball_ready, trace_impacts
from app.phases import PHASES, segment_swings
from app.pose import Joint, PoseVideo, pose_ready, read_pose

MAX_BYTES = 80 * 1024 * 1024
DISCLAIMER = (
    "Pose joints are from MediaPipe Pose Landmarker. "
    "Phases are placed from hand motion, not a trained swing classifier. "
    "Shaft and club-head boxes are not detected. "
    "The ball trace is kept only when the ball leaves the tee, and it stops when the detector loses the ball. "
    "This is an observation from the video, and there is no guaranteed certainty."
)


def analyze_bytes(data: bytes) -> dict:
    if not data:
        raise ValueError("The video file is empty.")
    if len(data) > MAX_BYTES:
        raise ValueError("Video is larger than 80 MB.")
    suffix = ".webm" if data[:4] == b"\x1a\x45\xdf\xa3" else ".mp4"
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        handle.write(data)
        handle.close()
        return analyze_path(handle.name)
    finally:
        Path(handle.name).unlink(missing_ok=True)


def analyze_path(path: str) -> dict:
    video = read_pose(path)
    measurement = measurement_from_pose(video)
    _attach_ball(measurement, path, video)
    return measurement


def measurement_from_pose(video: PoseVideo) -> dict:
    hand_y = [_hand_y(frame) for frame in video.frames]
    cue_sets = segment_swings(hand_y, height=video.height, fps=video.fps)
    swings = []
    for swing_index, cues in enumerate(cue_sets, start=1):
        address_y = hand_y[cues[0]]
        top_y = hand_y[cues[3]]
        rise = 0.0 if address_y is None or top_y is None else max(0.0, address_y - top_y)
        events = []
        for name, frame in zip(PHASES, cues, strict=True):
            joints = video.frames[frame]
            box = hands_box(joints, video.width, video.height)
            score = _score(joints, rise, video.height)
            events.append(
                {
                    "name": name,
                    "label": name,
                    "frame": frame,
                    "timeS": _time_s(video, frame),
                    "score": score,
                    "tentative": score < 0.6,
                    "angles": joint_angles(joints),
                    "clubs": {"shaft": None, "clubHead": None, "hands": _club(box)},
                    "joints": _dense(joints),
                }
            )
        swings.append({"id": swing_index, "events": events, "ball": []})
    return {
        "fps": video.fps,
        "width": video.width,
        "height": video.height,
        "poseModel": "mediapipe-pose-landmarker-lite",
        "phaseModel": "kinematic-v2",
        "clubModel": None,
        "ballModel": MODEL_NAME if ball_ready() is None else None,
        "disclaimer": DISCLAIMER,
        "frames": [_track_frame(frame, video.width, video.height) for frame in video.frames],
        "swings": swings,
    }


def download_video(url: str) -> bytes:
    if not url.startswith(("https://", "http://")):
        raise ValueError("The video URL must be http or https.")
    request = Request(url, headers={"User-Agent": "golfar-swing/1"})
    try:
        with urlopen(request, timeout=30) as response:
            chunks: list[bytes] = []
            total = 0
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > MAX_BYTES:
                    raise ValueError("Video is larger than 80 MB.")
                chunks.append(block)
    except URLError as exc:
        raise ValueError("The video URL could not be read.") from exc
    data = b"".join(chunks)
    if not data:
        raise ValueError("The video URL was empty.")
    return data


def hands_box(joints: list[Joint | None], width: int, height: int) -> list[int] | None:
    wrists = [joints[index] for index in (9, 10) if index < len(joints) and joints[index] is not None and joints[index][2] >= 0.5]
    if not wrists:
        return None
    pad = max(12, round(0.03 * width))
    return [
        max(0, round(min(joint[0] for joint in wrists) - pad)),
        max(0, round(min(joint[1] for joint in wrists) - pad)),
        min(width - 1, round(max(joint[0] for joint in wrists) + pad)),
        min(height - 1, round(max(joint[1] for joint in wrists) + pad)),
    ]


def _time_s(video: PoseVideo, frame: int) -> float:
    if frame < len(video.times):
        return round(video.times[frame], 4)
    return round(frame / video.fps, 4)


def _hand_y(joints: list[Joint | None]) -> float | None:
    wrists = [joints[index] for index in (9, 10) if index < len(joints) and joints[index] is not None and joints[index][2] >= 0.5]
    if not wrists:
        return None
    return sum(joint[1] for joint in wrists) / len(wrists)


def _track_frame(joints: list[Joint | None], width: int, height: int) -> dict:
    points = []
    for joint in joints:
        if joint is None or joint[2] < 0.5:
            points.append(None)
        else:
            points.append([round(joint[0]), round(joint[1])])
    return {"j": points, "s": None, "c": None, "h": hands_box(joints, width, height)}


def _club(box: list[int] | None) -> dict | None:
    if box is None:
        return None
    return {"confidence": 1, "box": box}


def _dense(joints: list[Joint | None]) -> list[list[float]]:
    dense = []
    for joint in joints:
        if joint is None:
            dense.append([0, 0, 0])
        else:
            dense.append([round(joint[0], 1), round(joint[1], 1), round(joint[2], 3)])
    return dense


def _score(joints: list[Joint | None], rise: float, height: int) -> float:
    visible = [joints[index][2] for index in (5, 6, 9, 10) if index < len(joints) and joints[index] is not None]
    visibility = sum(visible) / len(visible) if visible else 0.0
    lifted = min(1.0, rise / (0.15 * height)) if height else 0.0
    return round(min(0.99, 0.25 + 0.5 * visibility + 0.24 * lifted), 3)


def _attach_ball(measurement: dict, path: str, video: PoseVideo) -> None:
    impacts = []
    for swing in measurement["swings"]:
        impacts.append(next((event["frame"] for event in swing["events"] if event["name"] == "Impact"), None))
    traces = trace_impacts(path, impacts, fps=video.fps, times=video.times)
    for swing, trace in zip(measurement["swings"], traces, strict=True):
        swing["ball"] = trace


def runtime_status() -> dict:
    reason = pose_ready()
    ball_reason = ball_ready()
    return {"ok": True, "pose": reason is None, "ball": ball_reason is None, "detail": reason or ball_reason}
