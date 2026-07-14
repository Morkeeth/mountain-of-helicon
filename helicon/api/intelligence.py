"""API surface for the output/route/runs half - the intelligence layer that was
CLI-only. This is what makes the post-night-run loop (rate runs, see what to
optimise, pick the next run, which model to route to) usable in the dashboard/app
instead of the terminal. Read-only, cheap (persisted data + a capped git scan)."""
import os

from fastapi import APIRouter

from helicon.api.app import get_conn, get_config

router = APIRouter()


@router.get("/runs")
async def runs():
    """The Latest-runs surface: scored run-card history + suggestions (best run
    shape, model route, next run) read off it. The felt post-night-run view."""
    from helicon.runs import latest_run_cards, suggest_runs
    conn = get_conn()
    config = get_config()
    return {
        "cards": latest_run_cards(conn, limit=30),
        "suggest": suggest_runs(conn, config),
    }


@router.get("/route")
async def route_view(task_class: str | None = None, min_n: int = 5):
    """Model routing: which model has the best verified track record per
    task-class, Wilson-scored, with sample size + confidence."""
    from helicon.route import route
    conn = get_conn()
    return route(conn, task_class=task_class, min_n=min_n)


@router.get("/leaderboard")
async def leaderboard(max: int = 200, by_task: bool = False):
    """Population model-reliability from git history (survived vs reverted),
    across ~/CODE repos. Capped commit count keeps the request cheap."""
    from helicon.leaderboard import build_leaderboard
    code = os.path.expanduser("~/CODE")
    repos = ([os.path.join(code, d) for d in sorted(os.listdir(code))
              if os.path.isdir(os.path.join(code, d, ".git"))]
             if os.path.isdir(code) else [])
    return build_leaderboard(repos, max_commits=max, by_task=by_task)


@router.get("/route/evidence")
async def route_evidence(limit: int = 100):
    """The raw verified verdicts behind the routing read (provenance)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT model, harness, task_class, verdict, terminal, claim, receipt, created_at "
        "FROM route_evidence ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return {"evidence": [dict(r) for r in rows]}
