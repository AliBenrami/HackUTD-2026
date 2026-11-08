"""GolfAR swing analysis.

From backend/, with Python 3.11 or newer:

    python3.12 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

The phone reads EXPO_PUBLIC_SWING_API_URL, for example http://127.0.0.1:8000.
"""

from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.caddie import build_card, load_bag, narrate, recap, save_bag, save_note, save_swing, similar_swing
from app.golfstore import get_store
from app.pipeline import MAX_BYTES, analyze_bytes, download_video, runtime_status
from app.pose import PoseUnavailable
from app.swing_coach import PracticeCue, SwingCoachRequest, swing_coach

app = FastAPI(title="GolfAR swing analysis")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    status = runtime_status()
    try:
        status["golfStore"] = get_store().kind()
    except Exception as exc:
        status["golfStore"] = f"unavailable: {exc}"
    return status


def _user(user_id: str | None) -> str:
    if not user_id:
        raise HTTPException(status_code=400, detail="Sign in before saving golf notes.")
    return user_id


@app.get("/bag")
def read_bag(user_id: str) -> dict:
    return load_bag(_user(user_id))


@app.put("/bag")
def write_bag(body: dict) -> dict:
    return save_bag(_user(body.get("userId")), body.get("clubs") or [], body.get("handicapIndex"))


@app.get("/notes")
def read_notes(user_id: str, round_id: str | None = None) -> dict:
    query = {"userId": _user(user_id)}
    if round_id:
        query["roundId"] = round_id
    return {"notes": get_store().find("hole_notes", query)}


@app.put("/notes")
def write_note(body: dict) -> dict:
    return save_note(_user(body.get("userId")), body)


@app.post("/caddie/card")
def caddie_card(body: dict) -> dict:
    if "yards" not in body:
        raise HTTPException(status_code=400, detail="A hole yardage is required.")
    return build_card(_user(body.get("userId")), body)


@app.post("/caddie/recap")
def caddie_recap(body: dict) -> dict:
    saved = recap(_user(body.get("userId")), body)
    return saved or {"lines": None}


@app.get("/caddie/recap")
def read_recap(user_id: str, round_id: str) -> dict:
    found = get_store().find("rounds", {"userId": _user(user_id), "roundId": round_id})
    return found[0] if found else {"lines": None}


@app.post("/caddie/narrate")
def caddie_narrate(body: dict) -> dict:
    return narrate(body) or {"insights": None}


@app.post("/caddie/swing-coach")
async def caddie_swing_coach(body: SwingCoachRequest) -> PracticeCue | None:
    return await swing_coach(body)


@app.post("/swings")
def write_swing(body: dict) -> dict:
    if not body.get("videoId"):
        raise HTTPException(status_code=400, detail="A video id is required.")
    return save_swing(_user(body.get("userId")), body)


@app.post("/swings/similar")
def read_similar(body: dict) -> dict:
    vector = body.get("angleVector")
    if not isinstance(vector, list):
        raise HTTPException(status_code=400, detail="An angle vector is required.")
    return similar_swing(_user(body.get("userId")), str(body.get("videoId") or ""), vector)


@app.get("/weather")
def read_weather(course_id: str, lat: float | None = None, lng: float | None = None) -> dict:
    from app.caddie import course_weather

    center = {"lat": lat, "lng": lng} if lat is not None and lng is not None else None
    reading = course_weather(course_id, center)
    return {"wind": reading}


@app.post("/analyze")
async def analyze(
    video: UploadFile | None = File(default=None),
    url: str | None = Form(default=None),
) -> dict:
    data = await video.read() if video is not None else b""
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Video is larger than 80 MB.")
    if not data and not url:
        raise HTTPException(status_code=400, detail="Choose a video file or a video URL.")
    try:
        if not data:
            data = await run_in_threadpool(download_video, url or "")
        return await run_in_threadpool(analyze_bytes, data)
    except PoseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
