"""Read-only fleet API: what is running, what it cost, what still needs a human.

The suite is a multi-agent control plane, and `helicon/fleet.py` has been able to
answer "what is running right now" since it was written — but only into a
terminal. There was no route, so the desktop app could not ask. The Mac front
door was a ruling queue (HeliconApp.swift roots in QueueView) while the module
that knows about agents was reachable only from a shell.

Read-only on purpose. Nothing here starts, stops, or judges a run; it reports
what the store already knows. Every field traces to a table, and an empty fleet
returns an empty list rather than a reassuring summary — an idle machine is a
fact, not a health status.
"""
from fastapi import APIRouter

router = APIRouter()


def _conn():
    """Resolved lazily so this router stays independently importable, matching
    the workgraph router's seam."""
    from helicon.api.app import get_conn
    return get_conn()


@router.get("/fleet")
async def fleet(days: int = 7, limit: int = 50):
    """One payload for the front door: live runs, spend, unreviewed, efficiency."""
    from helicon import autogov, fleet as fleet_mod
    conn = _conn()
    days = max(1, min(days, 90))
    limit = max(1, min(limit, 200))
    live = fleet_mod.running(conn)
    return {
        "running": live,
        "running_count": len(live),
        # Split out because the two are not comparable: an observed run never
        # froze an objective, so it can never be measured against one.
        "observed_count": sum(1 for r in live if r.get("observed")),
        "spend": fleet_mod.spend_by_project(conn, days=days),
        "spend_window_days": days,
        "unreviewed": autogov.unreviewed(conn, limit=limit),
        "efficiency": fleet_mod.efficiency(conn),
    }
