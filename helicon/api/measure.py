"""The measurement series, as a surface.

Two endpoints, and the split between them is deliberate:

  GET  /api/measure   — reads what is ALREADY STORED. Never takes a reading.
  POST /api/measure   — takes a reading and stores it for this week.

Both are `async def`, which is not a style choice here: the shared sqlite
connection is created on the event loop thread by the app lifespan, and a plain
`def` endpoint runs in FastAPI's threadpool, where touching that connection
raises "SQLite objects created in a thread can only be used in that same
thread". Every other router in this package is async for the same reason.

A page load must not write a row. A surface that measured every time it was
opened would record four readings on a day it was glanced at four times, and one
week would render as four weeks of trend — the exact fake-precision defect the
detectors it records were built to catch. So recording is an explicit act with
its own verb, and the read path is honest about how old the number is.
"""
import os

from fastapi import APIRouter

from helicon.api.app import get_conn, get_config

router = APIRouter()


def _paths() -> dict:
    cfg = get_config() or {}
    ob = cfg.get("overboard", {}) if isinstance(cfg.get("overboard"), dict) else {}
    return {
        "catches": os.path.expanduser(ob.get("catches_path", "") or ""),
        "code_root": os.path.expanduser(ob.get("code_root", "") or ""),
        "repo": os.path.expanduser(ob.get("repo", "") or ""),
    }


@router.get("/measure")
async def measure(weeks: int = 12):
    """The stored series. Returns an empty metric list before the first
    recording rather than inventing a baseline — a chart drawn from no readings
    is a chart of nothing."""
    from helicon.measure import DIRECTION, LABELS, series

    data = series(get_conn(), weeks=weeks)
    for m in data["metrics"]:
        m["label"] = LABELS.get(m["metric"], m["metric"])
        m["direction"] = DIRECTION.get(m["metric"])
    data["recorded"] = bool(data["metrics"])
    return data


@router.post("/measure")
async def take_reading():
    """Record this week's reading. Re-running inside one week REPLACES that
    week's rows: a week read four times is still one week."""
    from helicon.measure import collect, record

    conn = get_conn()
    p = _paths()
    res = record(conn, collect(conn, p["catches"], "", p["code_root"], p["repo"]))
    res["configured"] = {k: bool(v) for k, v in p.items()}
    return res
