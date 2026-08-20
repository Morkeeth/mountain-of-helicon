"""The SETUP surface — thin API wrapper over helicon.setupcheck.

The census/chips logic lives in helicon/setupcheck.py (pure, shared with the
`helicon setup` CLI). This module owns only what is web-specific:

  - the rot.py cache idiom: a cached read is never silent — every response
    carries ran_at + cached, and ?fresh=1 forces a real walk (the census walks
    ~/.claude/projects, seconds not ms);
  - the measure.py doctrine: a page load must not write a row. GET reads;
    POST /snapshot records, and re-recording inside one day REPLACES that
    day's row.
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter

from helicon.api.app import get_conn, get_config
from helicon.setupcheck import axis2, census

router = APIRouter()

_TTL_S = 120
_cache: dict = {"res": None, "mono": 0.0, "ran_at": None, "took_s": None}

_SNAP_DDL = """CREATE TABLE IF NOT EXISTS setup_snapshots (
    day TEXT PRIMARY KEY,
    taken_at TEXT NOT NULL,
    skills INTEGER, routines INTEGER,
    memories_live INTEGER, memories_retired INTEGER,
    sessions INTEGER, context_bytes INTEGER,
    chips_pass INTEGER, chips_fail INTEGER, chips_unmeasured INTEGER
)"""


def _snapshots(conn) -> list[dict]:
    conn.execute(_SNAP_DDL)
    rows = conn.execute(
        "SELECT * FROM setup_snapshots ORDER BY day DESC LIMIT 60").fetchall()
    return [dict(r) for r in rows]


@router.get("/setup")
async def setup(fresh: int = 0):
    if not fresh and _cache["res"] is not None and \
            (time.monotonic() - _cache["mono"]) < _TTL_S:
        return {**_cache["res"], "ran_at": _cache["ran_at"],
                "took_s": _cache["took_s"], "cached": True,
                "snapshots": _snapshots(get_conn())}
    conn = get_conn()
    t0 = time.monotonic()
    cen = census(conn, get_config() or {})
    chips = axis2(conn, cen, get_config() or {})
    res = {"census": cen, "axis2": chips}
    took = round(time.monotonic() - t0, 2)
    _cache.update({"res": res, "mono": time.monotonic(), "took_s": took,
                   "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return {**res, "ran_at": _cache["ran_at"], "took_s": took, "cached": False,
            "snapshots": _snapshots(conn)}


@router.post("/setup/snapshot")
async def take_snapshot():
    """Record today's reading. Re-running inside one day REPLACES that day's
    row — a day glanced at four times is still one day (measure.py doctrine)."""
    conn = get_conn()
    conn.execute(_SNAP_DDL)
    cen = census(conn, get_config() or {})
    chips = axis2(conn, cen, get_config() or {})

    def _v(c):
        return c.get("value") if c.get("measured") else None

    always = sum(f["bytes"] for f in cen["context_files"] if f.get("exists"))
    verdicts = [c["verdict"] for c in chips]
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT OR REPLACE INTO setup_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (now.date().isoformat(), now.isoformat(timespec="seconds"),
         _v(cen["skills"]), _v(cen["routines"]),
         _v(cen["memories"]["live"]), _v(cen["memories"]["retired"]),
         _v(cen["sessions"]), always,
         verdicts.count("PASS"), verdicts.count("FAIL"),
         verdicts.count("UNMEASURED")))
    conn.commit()
    return {"recorded": now.date().isoformat(), "snapshots": _snapshots(conn)}
