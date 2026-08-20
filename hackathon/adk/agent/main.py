#!/usr/bin/env python3
"""Thin ADK agent — subprocess witness only. No probe logic here."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from firestore_store import latest_run, project_id, write_run

_AGENT_DIR = Path(__file__).resolve().parent
_DEFAULT_REPO = _AGENT_DIR.parent.parent.parent
REPO = Path(os.environ.get("HELICON_REPO", str(_DEFAULT_REPO)))
DEFAULT_DB = Path(
    os.environ.get(
        "HELICON_DEMO_DB",
        str(REPO / "hackathon" / "adk" / "demo" / "helicon.db"),
    )
)

app = FastAPI(title="Helicon Measurement Bench Agent", version="0.2.0")


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_bench(db_path: Path = DEFAULT_DB) -> tuple[int, str, str]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "helicon",
            "measurement-bench",
            "--json",
            "--db",
            str(db_path),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _trigger_from_request(request: Request) -> str:
    header = request.headers.get("X-Trigger", "").strip().lower()
    if header in ("pubsub", "manual"):
        return header
    return "manual"


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "firestore": project_id() is not None}


@app.get("/runs/latest")
def runs_latest():
    doc = latest_run()
    if doc is None:
        return JSONResponse(
            content={"error": "no runs in Firestore (GOOGLE_CLOUD_PROJECT unset or empty)"},
            status_code=404,
        )
    return JSONResponse(content=doc)


@app.post("/run")
def run(request: Request):
    run_id = str(uuid.uuid4())
    started_at = _iso_now()
    trigger = _trigger_from_request(request)
    code, stdout, stderr = _run_bench()
    finished_at = _iso_now()

    if code != 0:
        err_doc = {
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "trigger": trigger,
            "store_path": str(DEFAULT_DB),
            "status": "error",
            "error": stderr or f"exit {code}",
            "repro_command": "helicon measurement-bench --json --db hackathon/adk/demo/helicon.db",
        }
        try:
            write_run(run_id, err_doc)
        except Exception:
            pass
        return PlainTextResponse(stderr or f"exit {code}", status_code=500)

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return PlainTextResponse(
            f"invalid JSON from measurement-bench: {exc}\n{stdout}",
            status_code=500,
        )

    doc = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "trigger": trigger,
        "status": "ok",
        "error": None,
        "brief_text": None,
        **payload,
    }
    try:
        write_run(run_id, doc)
    except Exception as exc:
        return PlainTextResponse(f"Firestore write failed: {exc}", status_code=500)

    return JSONResponse(content=doc)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
