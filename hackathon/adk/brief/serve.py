#!/usr/bin/env python3
"""Serve brief UI — reads latest Firestore run or local /tmp/run.json fallback."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BRIEF_DIR = Path(__file__).resolve().parent
LOCAL_RUN = Path(os.environ.get("LOCAL_RUN_JSON", "/tmp/run.json"))
AGENT_URL = os.environ.get("AGENT_URL", "").rstrip("/")

app = FastAPI(title="Helicon Measurement Brief", version="0.1.0")


def _load_local_run() -> dict | None:
    if not LOCAL_RUN.is_file():
        return None
    try:
        return json.loads(LOCAL_RUN.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _load_firestore_run() -> dict | None:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        return None
    try:
        from google.cloud import firestore

        client = firestore.Client(project=project)
        docs = (
            client.collection("runs")
            .order_by("finished_at", direction=firestore.Query.DESCENDING)
            .limit(1)
            .stream()
        )
        for snap in docs:
            data = snap.to_dict() or {}
            data.setdefault("run_id", snap.id)
            return data
    except Exception:
        return None
    return None


@app.get("/api/run")
def api_run():
    doc = _load_firestore_run() or _load_local_run()
    if doc is None:
        return JSONResponse(
            content={
                "error": "no run found",
                "hint": "POST agent /run or run: python3 hackathon/adk/run_local.py -o /tmp/run.json",
            },
            status_code=404,
        )
    return JSONResponse(content=doc)


@app.get("/")
def index():
    return FileResponse(BRIEF_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(BRIEF_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
