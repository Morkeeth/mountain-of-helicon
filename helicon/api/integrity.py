"""Memory-integrity API — the data behind the tesserae mountain.

Surfaces the two integrity signals as JSON for the dashboard:
  - battery: run the context-quality battery over the real benchmark task set
    (eval._build_test_queries, derived from approved cubes) and return the
    per-task HEALTHY / DEGRADED / BROKEN verdicts. This is the live version of
    scripts/battery_report.py — real memory, no fixture.
  - snapshots: check_all() regression results vs captured baselines (empty until
    a baseline is captured with `helicon snapshot add`).

Both are computed live on the real DB. Nothing here is synthetic.
"""
import os
import re
from collections import Counter
from itertools import combinations

from fastapi import APIRouter

from helicon.api.app import get_conn
from helicon.battery import run_battery
from helicon.eval import _build_test_queries
from helicon.snapshots import check_all
from helicon.connectors import skills as skills_connector

router = APIRouter()

K = 5

_SKILL_ROOTS = [
    "~/.claude/skills",
    "~/.claude/plugins/marketplaces/claude-plugins-official",
]
_WORD = re.compile(r"[A-Za-z0-9]+")
_STOP = set("the a an and or to of for with when use used using this that your you "
            "on in at is are be it as if from into via can will not no do does".split())


def _terms(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "")
            if len(w) > 2 and w.lower() not in _STOP}


@router.get("/integrity/battery")
async def integrity_battery(llm: bool = False):
    """Live context-quality battery over the real benchmark tasks. With ?llm=true
    the Contradiction/Grounding tests are judged live by Qwen (slower, needs a
    key); default is deterministic-only for a fast dashboard load."""
    conn = get_conn()
    client = model = None
    if llm:
        from helicon.api.app import get_config
        from helicon.qwen import get_client, resolve_model
        config = get_config()
        client = get_client(config)
        model = resolve_model("default", config)
    queries = _build_test_queries(conn)
    tasks = []
    counts = Counter()
    for q in queries:
        res = run_battery(conn, q["query"], k=K, client=client, model=model or "qwen3.6-plus")
        counts[res["verdict"]] += 1
        tasks.append({
            "task": res["task"],
            "verdict": res["verdict"],
            "results": res["results"],
            "retrieved": res["retrieved"],
            "context_tokens": res["context_tokens"],
        })
    total = len(tasks)
    if total:
        from helicon.db import record_battery_point
        record_battery_point(
            conn, total, counts["HEALTHY"], counts["DEGRADED"], counts["BROKEN"],
            mean_tokens=sum(t["context_tokens"] for t in tasks) // total,
            source="dashboard")
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


@router.get("/integrity/history")
async def integrity_history():
    """The degradation-over-time curve: every recorded battery run, oldest
    first. Real points only — one per dashboard load or report run; no
    interpolation, no backfill."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT recorded_at, total, healthy, degraded, broken, mean_tokens, source "
        "FROM battery_history ORDER BY recorded_at"
    ).fetchall()
    points = [dict(r) for r in rows]
    for p in points:
        p["healthy_share"] = round(p["healthy"] / p["total"], 3) if p["total"] else None
    return {"points": points, "total": len(points)}


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


@router.get("/integrity/skills")
async def integrity_skills():
    """Audit the local Agent-Skills library for dead weight (real, no ground truth).
    Skills are the newest durable agent-memory surface; nobody regression-tests
    them. Same lens as retrieved memory, aimed at SKILL.md."""
    # Gated on the configured skills connector: a demo/keyless store (connectors
    # {}) must never scan the host's real ~/.claude/skills. Off -> empty audit.
    from helicon.api.app import get_config
    sk = (get_config().get("connectors") or {}).get("skills") or {}
    if not sk.get("enabled"):
        return {"roots": [], "files": 0, "unique": 0, "duplicates": [],
                "collisions": [], "thin": [],
                "summary": {"duplicated": 0, "collisions": 0, "thin": 0},
                "note": "skills connector not configured"}
    roots = [r for r in (sk.get("skill_roots") or _SKILL_ROOTS)
             if os.path.exists(os.path.expanduser(r))]
    found = skills_connector.scan({"skill_roots": roots})

    meta = []
    for r in found:
        name = r.metadata["skill_name"]
        desc = r.metadata["description"]
        meta.append({
            "name": name,
            "desc_len": r.metadata["desc_len"],
            "trigger_terms": _terms(f"{name} {desc}"),
            "path": r.metadata["path"],
        })

    # exact duplicates: same skill name installed in multiple places
    by_name = {}
    for m in meta:
        by_name.setdefault(m["name"].lower(), []).append(m)
    duplicates = [
        {"name": g[0]["name"], "count": len(g), "paths": [x["path"] for x in g][:6]}
        for g in by_name.values() if len(g) > 1
    ]
    duplicates.sort(key=lambda d: -d["count"])

    uniq = list({m["name"].lower(): m for m in meta}.values())

    # trigger collisions among distinct skills
    collisions = []
    for a, b in combinations(uniq, 2):
        t1, t2 = a["trigger_terms"], b["trigger_terms"]
        if t1 and t2:
            j = len(t1 & t2) / len(t1 | t2)
            if j > 0.5:
                collisions.append({"a": a["name"], "b": b["name"], "overlap": round(j, 2)})
    collisions.sort(key=lambda c: -c["overlap"])

    thin = [{"name": m["name"], "desc_len": m["desc_len"]}
            for m in uniq if m["desc_len"] < 40]

    return {
        "roots": roots,
        "files": len(meta),
        "unique": len(uniq),
        "duplicates": duplicates,
        "collisions": collisions,
        "thin": thin,
        "summary": {
            "duplicated": len(duplicates),
            "collisions": len(collisions),
            "thin": len(thin),
        },
    }
