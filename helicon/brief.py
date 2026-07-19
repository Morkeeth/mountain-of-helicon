"""The morning brief — the product vision in one screen.

VISION.md's north-star: "It is 9am. Helicon tells you: two memories are no longer
trustworthy, one project is waiting on a decision, yesterday's expensive model did
not outperform the cheaper one for this task class, and these are the three next
actions worth your attention."

`build_brief` assembles all five pillars into one honest object:

  Truth       — what the record no longer stands behind (open rulings, stale, grade)
  Continuity  — what verified context is carried across runs
  Direction   — which model actually earned its cost (Wilson-scored, or insufficient)
  Reflection  — what changed since the last look (rulings applied, runs scored)
  Calm        — the few things worth a human's judgment, not three hundred

Every section degrades honestly: empty → "nothing", thin evidence → "insufficient",
never a fabricated number. It is surface-agnostic and READ-ONLY — the CLI prints it,
the MCP serves it to an agent, the dashboard and macOS app render the same object.
"""

from helicon.score import compute_score


def _rows(conn, sql, params=()):
    try:
        return conn.execute(sql, params).fetchall()
    except Exception:
        return []


def _scalar(conn, sql, params=(), default=0):
    try:
        r = conn.execute(sql, params).fetchone()
        return r[0] if r else default
    except Exception:
        return default


def build_brief(conn, config=None, limit: int = 3) -> dict:
    """Assemble the five-pillar brief. `conn` should have row_factory = sqlite3.Row."""

    # ---- TRUTH: what the record no longer stands behind ----
    open_findings = _rows(
        conn,
        "SELECT id, finding, severity FROM audit_log "
        "WHERE audit_type='factual' AND human_decision IS NULL "
        "ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
        "WHEN 'medium' THEN 2 ELSE 3 END, audited_at DESC",
    )
    stale = _rows(
        conn,
        "SELECT id, title, confidence FROM helicon_cubes "
        "WHERE merged_into IS NULL AND review_status IN ('approved','pending') "
        "AND confidence < 0.15 ORDER BY confidence ASC LIMIT ?",
        (limit,),
    )
    grade = compute_score(conn)
    truth = {
        "grade": grade.get("score"),
        "reviewed": grade.get("reviewed"),
        "total": grade.get("total"),
        "no_longer_trustworthy": [
            {"id": r["id"], "title": r["title"], "confidence": round(r["confidence"], 3)}
            for r in stale
        ],
        "stale_count": _scalar(
            conn,
            "SELECT COUNT(*) FROM helicon_cubes WHERE merged_into IS NULL "
            "AND review_status IN ('approved','pending') AND confidence < 0.15",
        ),
        "headline": None,  # filled below
    }

    # ---- CALM: the few things worth a human's judgment ----
    exceptions = [
        {"id": r["id"], "finding": (r["finding"] or "")[:160], "severity": r["severity"]}
        for r in open_findings
        if r["severity"] in ("critical", "high")
    ]
    calm = {
        "open_exceptions": len(open_findings),
        "worth_your_judgment": exceptions[:limit],
        "headline": (
            f"{len(exceptions)} exception(s) need a ruling"
            if exceptions
            else ("nothing needs a ruling right now" if not open_findings
                  else f"{len(open_findings)} low-severity finding(s), none urgent")
        ),
    }

    # ---- DIRECTION: which model earned its cost ----
    direction = {"task_classes": [], "headline": "no routing evidence yet — run `helicon route --record --run`"}
    try:
        from helicon.route import route

        routed = route(conn)
        picks = []
        for r in routed.get("results", []):
            if r.get("recommendation") or r.get("lean"):
                picks.append(
                    {
                        "task_class": r["task_class"],
                        "recommendation": r.get("recommendation"),
                        "lean": r.get("lean"),
                        "sufficient": r.get("sufficient"),
                    }
                )
        if picks:
            direction["task_classes"] = picks[:limit]
            firm = [p for p in picks if p["sufficient"]]
            direction["headline"] = (
                f"{firm[0]['recommendation']} leads for {firm[0]['task_class']}"
                if firm
                else "provisional leans only — not enough verdicts for a firm route"
            )
        elif routed.get("results"):
            direction["headline"] = "insufficient evidence for any route — need more verified verdicts"
    except Exception:
        pass

    # ---- REFLECTION: what changed since the last look ----
    recent_batches = _rows(
        conn,
        "SELECT id, applied_at FROM govern_batches WHERE undone_at IS NULL "
        "ORDER BY applied_at DESC LIMIT ?",
        (limit,),
    )
    recent_runs = _rows(
        conn,
        "SELECT run_id, model, score, verified_ratio, cost FROM run_cards "
        "ORDER BY scored_at DESC LIMIT ?",
        (limit,),
    )
    reflection = {
        "rulings_applied": [
            {"id": r["id"], "at": (r["applied_at"] or "")[:16]} for r in recent_batches
        ],
        "runs_scored": [
            {
                "run_id": r["run_id"],
                "model": r["model"],
                "score": r["score"],
                "verified_ratio": r["verified_ratio"],
                "cost": r["cost"],
            }
            for r in recent_runs
        ],
        "headline": (
            f"{len(recent_batches)} ruling(s) applied, {len(recent_runs)} run(s) scored recently"
            if (recent_batches or recent_runs)
            else "nothing changed since the last look"
        ),
    }

    # ---- CONTINUITY: verified context carried across runs ----
    continuity = {
        "context_packets": _scalar(conn, "SELECT COUNT(*) FROM context_packets"),
        "task_runs": _scalar(conn, "SELECT COUNT(*) FROM task_runs"),
        "headline": None,
    }
    continuity["headline"] = (
        f"{continuity['context_packets']} context packet(s) recorded across {continuity['task_runs']} run(s)"
        if continuity["context_packets"]
        else "no context carried yet — the recorder is armed, nothing captured"
    )

    # Truth headline last (it summarises the store's standing)
    ntw = truth["stale_count"]
    truth["headline"] = (
        f"grade {truth['grade']} · {ntw} memor{'y' if ntw == 1 else 'ies'} no longer trustworthy"
        if ntw
        else f"grade {truth['grade']} · nothing below the trust floor"
    )

    return {
        "truth": truth,
        "continuity": continuity,
        "direction": direction,
        "reflection": reflection,
        "calm": calm,
    }


def format_brief(b: dict) -> str:
    """Human-readable rendering for the CLI — the 9am screen."""
    L = ["\n  ── Mount Helicon · morning brief ─────────────────────────────"]
    L.append(f"\n  TRUTH       {b['truth']['headline']}")
    for m in b["truth"]["no_longer_trustworthy"]:
        L.append(f"                ↓ [{m['id']}] {m['title']}  (conf {m['confidence']})")

    L.append(f"\n  CALM        {b['calm']['headline']}")
    for e in b["calm"]["worth_your_judgment"]:
        L.append(f"                • [{e['severity']}] #{e['id']} {e['finding']}")

    L.append(f"\n  DIRECTION   {b['direction']['headline']}")
    for p in b["direction"]["task_classes"]:
        pick = p["recommendation"] or f"{p['lean']} (lean)"
        L.append(f"                → {p['task_class']}: {pick}")

    L.append(f"\n  REFLECTION  {b['reflection']['headline']}")
    for r in b["reflection"]["runs_scored"]:
        L.append(f"                · run {r['run_id']}: {r['model']} score {r['score']} (${r['cost']})")

    L.append(f"\n  CONTINUITY  {b['continuity']['headline']}")
    L.append("\n  ──────────────────────────────────────────────────────────────\n")
    return "\n".join(L)
