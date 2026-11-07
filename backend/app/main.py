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

from app.pipeline import MAX_BYTES, analyze_bytes, download_video, runtime_status
from app.pose import PoseUnavailable

app = FastAPI(title="GolfAR swing analysis")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return runtime_status()


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
