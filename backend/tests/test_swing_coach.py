import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import swing_coach
from app.main import app


EVIDENCE = {
    "id": "reference:Top:leadElbow",
    "observation": "The lead elbow reads 120° at the top.",
    "why": "The reference has a little less bend here.",
}


@pytest.fixture
def client(monkeypatch):
    for name in ("NVIDIA_API_KEY", "NEMOTRON_BASE_URL", "NEMOTRON_MODEL"):
        monkeypatch.delenv(name, raising=False)
    return TestClient(app)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (json.dumps({"evidenceId": EVIDENCE["id"], "cue": "Pause at the top with a relaxed lead arm."}), True),
        (json.dumps({"evidenceId": "invented", "cue": "Practice slowly."}), False),
        ("not JSON", False),
    ],
)
def test_swing_coach_validates_provider_output(client, monkeypatch, content, expected):
    def respond(request):
        assert request.url == httpx.URL("https://integrate.api.nvidia.com/v1/chat/completions")
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == swing_coach.DEFAULT_MODEL
        assert payload["stream"] is False
        assert json.loads(payload["messages"][1]["content"]) == {"evidence": [EVIDENCE]}
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    provider = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(swing_coach.httpx, "AsyncClient", lambda: provider)
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    response = client.post("/caddie/swing-coach", json={"evidence": [EVIDENCE]})
    assert response.status_code == 200
    assert response.json() == (json.loads(content) if expected else None)


def test_swing_coach_times_out(client, monkeypatch):
    async def respond(request):
        await asyncio.sleep(1)
        raise AssertionError("Provider should have been cancelled")

    provider = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(swing_coach.httpx, "AsyncClient", lambda: provider)
    monkeypatch.setattr(swing_coach, "COACH_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setenv("NEMOTRON_BASE_URL", "http://localhost:9000/v1")
    response = client.post("/caddie/swing-coach", json={"evidence": [EVIDENCE]})
    assert response.status_code == 200
    assert response.json() is None


def test_swing_coach_without_provider(client):
    response = client.post("/caddie/swing-coach", json={"evidence": [EVIDENCE]})
    assert response.status_code == 200
    assert response.json() is None
