import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["GOLF_STORE_PATH"] = str(Path(__file__).parent / "_golf.json")
os.environ.pop("MONGODB_URI", None)
os.environ.pop("GEMINI_API_KEY", None)

from app.golfstore import FileStore, set_store
from app.main import app

set_store(FileStore(Path(os.environ["GOLF_STORE_PATH"])))
client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store():
    Path(os.environ["GOLF_STORE_PATH"]).write_text("{}")


def test_fallback_card_is_saved_without_a_model():
    response = client.post(
        "/caddie/card",
        json={
            "userId": "player-1",
            "roundId": "round-1",
            "courseId": "cedar-ridge",
            "holeNumber": 3,
            "par": 3,
            "yards": 160,
            "pin": "front",
            "windOn": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "fallback"
    assert body["club"] == "7-iron"
    assert body["adjustedYards"] == 155
    runs = client.get("/notes", params={"user_id": "player-1"}).json()
    assert runs["notes"] == []


def test_hole_notes_feed_the_bag_tendencies():
    saved = client.put(
        "/notes",
        json={
            "userId": "player-1",
            "roundId": "round-1",
            "holeNumber": 3,
            "par": 3,
            "strokes": 4,
            "sample": False,
            "miss": "right",
            "gir": False,
            "pin": "middle",
            "shots": [{"n": 1, "lng": -96.7, "lat": 32.99, "source": "tap"}],
        },
    )
    assert saved.status_code == 200
    bag = client.get("/bag", params={"user_id": "player-1"}).json()
    assert bag["tendencies"]["holes"] == 1
    assert bag["tendencies"]["misses"]["right"] == 1
    assert bag["starter"] is True


def test_similar_swing_rejects_a_distant_neighbor():
    vector = [150] * 16
    client.post("/swings", json={"userId": "player-1", "videoId": "a", "club": "7-iron", "angleVector": vector})
    other = [90] * 16
    client.post("/swings", json={"userId": "player-1", "videoId": "b", "club": "Driver", "angleVector": other})
    close = client.post("/swings/similar", json={"userId": "player-1", "videoId": "a", "angleVector": vector}).json()
    assert close["close"] is False
