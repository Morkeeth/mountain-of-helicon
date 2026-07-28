from fastapi import APIRouter

from helicon.api.app import get_conn, get_config
from helicon.brief import build_brief
from helicon.reflection import day_reflection

router = APIRouter()


@router.get("/brief")
async def get_brief(limit: int = 3):
    """The morning brief — all five pillars in one read-only object. The dashboard
    Brief tab and the macOS menu-bar app both render this."""
    conn = get_conn()
    config = get_config()
    return build_brief(conn, config, limit=limit)


@router.get("/reflection/day")
async def get_day_reflection(day: str = ""):
    """Reflection pillar — one real day of runs rolled up (outcomes, cost,
    scored cards, rulings). Read-only. `day` is YYYY-MM-DD; omitted = the latest
    day with activity."""
    return day_reflection(get_conn(), day=day or None)
