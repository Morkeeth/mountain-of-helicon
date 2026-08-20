#!/usr/bin/env python3
"""Thin ADK agent — subprocess witness only. No probe logic here."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, Response

_AGENT_DIR = Path(__file__).resolve().parent
_DEFAULT_REPO = _AGENT_DIR.parent.parent.parent
REPO = Path(os.environ.get("HELICON_REPO", str(_DEFAULT_REPO)))
DEFAULT_DB = Path(
    os.environ.get(
        "HELICON_DEMO_DB",
        str(REPO / "hackathon" / "adk" / "demo" / "helicon.db"),
    )
)

app = FastAPI(title="Helicon Measurement Bench Agent", version="0.1.0")


def _run_bench(db_path: Path | None = None) -> tuple[int, str, str]:
    db_path = db_path or DEFAULT_DB
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


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/run")
def run():
    code, stdout, stderr = _run_bench()
    if code != 0:
        return PlainTextResponse(stderr or f"exit {code}", status_code=500)

    try:
        json.loads(stdout)
    except json.JSONDecodeError as exc:
        return PlainTextResponse(
            f"invalid JSON from measurement-bench: {exc}\n{stdout}",
            status_code=500,
        )
    return Response(content=stdout, media_type="application/json")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
