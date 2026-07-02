"""Memory-integrity API — the data behind the tesserae mountain.

Surfaces the two integrity signals as JSON for the dashboard:
  - battery: run the context-quality battery over the real benchmark task set
    (eval._build_test_queries, derived from approved cubes) and return the
    per-task HEALTHY / DEGRADED / BROKEN verdicts. This is the live version of
    scripts/battery_report.py — real memory, no fixture.
  - snapshots: check_all() regression results vs captured baselines (empty until
    a baseline is captured with `glaze snapshot add`).

Both are computed live on the real DB. Nothing here is synthetic.
"""
from collections import Counter

from fastapi import APIRouter

from glaze.api.app import get_conn
from glaze.battery import run_battery
from glaze.eval import _build_test_queries
from glaze.snapshots import check_all

router = APIRouter()

K = 5


@router.get("/integrity/battery")
async def integrity_battery():
    """Live context-quality battery over the real benchmark tasks."""
    conn = get_conn()
    queries = _build_test_queries(conn)
    tasks = []
    counts = Counter()
    for q in queries:
        res = run_battery(conn, q["query"], k=K)
        counts[res["verdict"]] += 1
        tasks.append({
            "task": res["task"],
            "verdict": res["verdict"],
            "results": res["results"],
            "retrieved": res["retrieved"],
        })
    total = len(tasks)
    return {
        "top_k": K,
        "total": total,
        "summary": {
            "healthy": counts["HEALTHY"],
            "degraded": counts["DEGRADED"],
            "broken": counts["BROKEN"],
        },
        "tasks": tasks,
    }


@router.get("/integrity/snapshots")
async def integrity_snapshots():
    """Regression check of every captured context snapshot vs current memory."""
    conn = get_conn()
    results = check_all(conn)
    regressed = sum(1 for r in results if r["regressed"])
    return {
        "total": len(results),
        "regressed": regressed,
        "clean": len(results) - regressed,
        "snapshots": results,
    }
