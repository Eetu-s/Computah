"""Minimal HTTP transcription service.

Endpoints:
    GET  /health       -> {"status": "ok", "model": "..."}
    POST /transcribe   -> multipart file upload; returns {"text": "..."}

Run locally:
    uvicorn app.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import io
import time

from fastapi import FastAPI, File, HTTPException, UploadFile

from .core import DEFAULT_MODEL, load_audio, load_transcriber, transcribe_samples

app = FastAPI(title="Moonshine STT", version="1.0.0")


@app.on_event("startup")
def _warm_up() -> None:
    # Load the model once at startup so the first request isn't slow.
    load_transcriber()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": DEFAULT_MODEL}


@app.post("/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    try:
        samples, sample_rate = load_audio(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=415,
            detail=f"could not decode audio: {exc}",
        ) from exc

    start = time.perf_counter()
    text = transcribe_samples(samples, sample_rate)
    elapsed = time.perf_counter() - start

    return {
        "text": text,
        "model": DEFAULT_MODEL,
        "seconds": round(elapsed, 3),
    }
