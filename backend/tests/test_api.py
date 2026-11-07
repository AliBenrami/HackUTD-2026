from fastapi.testclient import TestClient

from app.main import app
from app.pipeline import download_video, measurement_from_pose
from app.pose import PoseVideo


def _pose() -> PoseVideo:
    frames = []
    for index in range(90):
        joints = [None] * 17
        # Wrists travel through the synthetic swing. Shoulders and hips stay put.
        hand_y = 800.0
        if 10 <= index <= 30:
            hand_y = 800 - (800 - 200) * (index - 10) / 20
        elif 31 <= index <= 45:
            hand_y = 200 + (820 - 200) * (index - 30) / 15
        elif 46 <= index <= 70:
            hand_y = 820 - (820 - 300) * (index - 45) / 25
        elif index > 70:
            hand_y = 300
        joints[5] = (200, 300, 0.9)
        joints[6] = (260, 300, 0.9)
        joints[7] = (180, 420, 0.9)
        joints[8] = (280, 420, 0.9)
        joints[9] = (190, hand_y, 0.95)
        joints[10] = (250, hand_y, 0.95)
        joints[11] = (210, 600, 0.9)
        joints[12] = (250, 600, 0.9)
        frames.append(joints)
    return PoseVideo(fps=30, width=1080, height=1920, frames=frames)


def test_measurement_hides_the_club_and_names_the_models():
    body = measurement_from_pose(_pose())
    assert body["poseModel"] == "mediapipe-pose-landmarker-lite"
    assert body["phaseModel"] == "kinematic-v2"
    assert body["clubModel"] is None
    assert body["frames"][0]["s"] is None
    assert body["frames"][0]["c"] is None
    assert body["frames"][30]["h"] is not None
    assert body["swings"][0]["events"][3]["name"] == "Top"
    assert "no guaranteed certainty" in body["disclaimer"]


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_analyze_rejects_an_empty_file():
    response = TestClient(app).post("/analyze", files={"video": ("swing.mp4", b"", "video/mp4")})
    assert response.status_code == 400


def test_analyze_returns_the_pipeline_result(monkeypatch):
    monkeypatch.setattr("app.main.analyze_bytes", lambda data: {"fps": 30, "frames": [], "swings": [], "received": len(data)})
    response = TestClient(app).post("/analyze", files={"video": ("swing.mp4", b"not-a-video", "video/mp4")})
    assert response.status_code == 200
    assert response.json()["received"] == len(b"not-a-video")


def test_download_rejects_a_local_file():
    try:
        download_video("file:///tmp/swing.mp4")
    except ValueError as exc:
        assert "http" in str(exc)
    else:
        raise AssertionError("A file URL should be rejected.")
