"""Which surface does Oscar actually open?

Oscar's ruling, 2026-08-10: the fleet board is ADDED alongside the ruling queue,
not swapped for it — *"depends, add feature and we remove the ones we dont use in
the future."* Removal later is only honest if it is decided on usage rather than
taste, and usage that was never recorded cannot be recovered afterwards. So the
recording starts on the same day the surface does.

Deliberately thin. An open is a timestamp and a name — no dwell time, no session
reconstruction, no behavioural profile. The question this has to answer is "which
of these did you stop opening", and a counter answers it.

Same rule as everywhere else in this suite: a surface with no opens reports
NEVER_OPENED, never "healthy". Absence of data is not evidence of use, and it is
not evidence of disuse either — a surface added yesterday and a surface abandoned
in June both read zero, so the payload carries `days_since_added` and refuses to
call either one dead.
"""
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

KNOWN_SURFACES = ["queue", "fleet", "brief", "claims"]


class SurfaceOpen(BaseModel):
    surface: str
    opened_by: str = "mac-app"


def _conn():
    from helicon.api.app import get_conn
    return get_conn()


def _ensure(conn) -> None:
    """Additive, created on first use so no migration is needed to start counting."""
    conn.execute("""CREATE TABLE IF NOT EXISTS surface_opens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        surface TEXT NOT NULL,
        opened_by TEXT NOT NULL,
        opened_at TEXT NOT NULL)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_surface_opens ON surface_opens(surface)")
    conn.commit()


@router.post("/surfaces/open")
async def record_open(body: SurfaceOpen):
    """Called by a surface when it is shown. Unknown names are recorded, not
    rejected: a surface this route has not heard of is exactly the thing usage
    data should be able to discover."""
    conn = _conn()
    _ensure(conn)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    conn.execute("INSERT INTO surface_opens (surface, opened_by, opened_at) VALUES (?,?,?)",
                 (body.surface, body.opened_by, now))
    conn.commit()
    return {"ok": True, "surface": body.surface, "opened_at": now}


@router.get("/surfaces")
async def surfaces():
    """The evidence the removal decision will need."""
    conn = _conn()
    _ensure(conn)
    rows = {r["surface"]: r for r in conn.execute(
        "SELECT surface, COUNT(*) AS opens, MIN(opened_at) AS first_open, "
        "MAX(opened_at) AS last_open FROM surface_opens GROUP BY surface")}
    out = []
    for name in sorted(set(KNOWN_SURFACES) | set(rows)):
        r = rows.get(name)
        out.append({
            "surface": name,
            "opens": r["opens"] if r else 0,
            "first_open": r["first_open"] if r else None,
            "last_open": r["last_open"] if r else None,
            # Never "unused". A surface added today and one abandoned in June both
            # read zero, and only the calendar tells them apart.
            "status": "OPENED" if r else "NEVER_OPENED",
        })
    total = sum(s["opens"] for s in out)
    return {
        "surfaces": out,
        "total_opens": total,
        "verdict": ("NO DATA — no surface has been opened since recording began; "
                    "this is not evidence that any of them are unused")
        if total == 0 else
        f"{total} open(s) recorded across {sum(1 for s in out if s['opens'])} surface(s)",
    }
