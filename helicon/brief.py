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

import re

from helicon.score import compute_score


def _humanize(text: str) -> str:
    """Turn a machine finding into a plain sentence a tired human can read.
    Already-human findings (the demo's Stripe line) pass through untouched."""
    t = (text or "").strip()
    m = re.match(r"(?:Cross-source (?:claim conflict|contradiction)|[^:]*conflict):\s*(.+)", t)
    if m:
        t = m.group(1)
    t = re.sub(r"\s*\[[^\]]*\]", "", t)                       # drop [scope] noise
    t = re.sub(r"\s*\(\d+\s*(?:claim|cube|memor(?:y|ies))\(?s?\)?\)", "", t)  # drop (n claims)
    m2 = re.match(r"(.+?)\s+[—-]\s+(.+?)\s+vs\.?\s+(.+)", t)  # "TOPIC — A vs B"
    if m2:
        topic, a, rest = (g.strip() for g in m2.groups())
        rest = re.sub(r"\s+vs\.?\s+", ", ", rest)
        return f"Your notes disagree on {topic}: is it {a} or {rest}?"
    return t


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
        {"id": r["id"], "finding": _humanize(r["finding"]), "severity": r["severity"]}
        for r in open_findings
        if r["severity"] in ("critical", "high")
    ]
    n_exc = len(exceptions)
    calm = {
        "open_exceptions": len(open_findings),
        "worth_your_judgment": exceptions[:limit],
        "headline": (
            f"{n_exc} thing{'' if n_exc == 1 else 's'} to decide"
            if exceptions
            else ("Nothing needs you right now." if not open_findings
                  else f"{len(open_findings)} small thing(s) to look at, none urgent")
        ),
    }

    # ---- DIRECTION: which model earned its cost ----
    direction = {"task_classes": [], "headline": "No model comparisons yet."}
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
                f"For {firm[0]['task_class']} work, {firm[0]['recommendation']} has the best track record"
                if firm
                else "Early signal only — not enough runs to call it yet"
            )
        elif routed.get("results"):
            direction["headline"] = "Not enough verified runs to recommend a model yet"
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
            f"{len(recent_runs)} run{'' if len(recent_runs) == 1 else 's'} scored since you last looked"
            if recent_runs
            else (f"{len(recent_batches)} decision{'' if len(recent_batches) == 1 else 's'} recorded recently"
                  if recent_batches else "Nothing's changed since you last looked.")
        ),
    }

    # ---- CONTINUITY: verified context carried across runs ----
    continuity = {
        "context_packets": _scalar(conn, "SELECT COUNT(*) FROM context_packets"),
        "task_runs": _scalar(conn, "SELECT COUNT(*) FROM task_runs"),
        "headline": None,
    }
    continuity["headline"] = (
        f"{continuity['context_packets']} piece(s) of context carried between runs"
        if continuity["context_packets"]
        else "Nothing carried between runs yet."
    )

    # Truth headline last (it summarises the store's standing)
    ntw = truth["stale_count"]
    truth["headline"] = (
        f"{ntw} memor{'y' if ntw == 1 else 'ies'} have gone stale"
        if ntw
        else "Your memory is holding — nothing stale."
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
