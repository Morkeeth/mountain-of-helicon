"""Reflection — a real DAY of agent work, rolled up honestly.

VISION.md's Reflection pillar, "Next": *the morning reflection surface across a
real day of runs*. The brief already carries a one-line Reflection headline and
the last few scored cards; this is the layer under it — the day itself:

  · every governed / observed run opened that day, with its outcome
    (accepted · rework · rollback · still needs your verdict)
  · what it changed (artifact count) and what it cost (known tokens, or
    'unknown' — never fabricated as 0)
  · the scored run cards for the day (yield / cost / score)
  · the rulings applied that day

Read-only and surface-agnostic: the CLI prints it, the API serves it, and the
brief embeds it. Every number traces to task_runs / run_cards / run_events /
govern_batches — nothing is invented, and an empty day says so.
"""
import json
import sqlite3


def _rows(conn, sql, params=()):
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []


def _scalar(conn, sql, params=(), default=None):
    try:
        r = conn.execute(sql, params).fetchone()
        return r[0] if r and r[0] is not None else default
    except sqlite3.Error:
        return default


def _day(ts: str | None) -> str:
    return (ts or "")[:10]


def latest_activity_day(conn) -> str | None:
    """The most recent day with ANY run activity: a run opened, a card scored, or
    a ruling applied. Returned as YYYY-MM-DD, or None when the store is empty."""
    candidates = [
        _scalar(conn, "SELECT MAX(opened_at) FROM task_runs"),
        _scalar(conn, "SELECT MAX(start) FROM run_cards"),
        _scalar(conn, "SELECT MAX(applied_at) FROM govern_batches WHERE undone_at IS NULL"),
    ]
    days = sorted({_day(c) for c in candidates if c}, reverse=True)
    return days[0] if days else None


_OUTCOME = {"accepted": "accepted", "rework": "rework", "rollback": "rollback"}


def _provenance(task_class: str | None) -> str:
    return "observed" if task_class == "auto-observed" else "forward"


def _run_tokens(cost_observation: str | None) -> tuple[int | None, bool]:
    """(known_total_tokens, is_known) from a task_run's cost_observation JSON.

    A missing or non-'known' observation is 'unknown' — never coerced to 0, which
    would read as 'this run was free'."""
    try:
        obs = json.loads(cost_observation or "{}")
    except (json.JSONDecodeError, TypeError):
        return None, False
    if obs.get("status") != "known":
        return None, False
    tokens = obs.get("total_tokens")
    if tokens is None:
        inner = obs.get("tokens") or {}
        tokens = inner.get("total") if isinstance(inner, dict) else None
    if isinstance(tokens, (int, float)):
        return int(tokens), True
    return None, False


def day_reflection(conn, day: str | None = None) -> dict:
    """Roll up one day of runs. `day` is YYYY-MM-DD; defaults to the most recent
    day with activity. `conn` should have row_factory = sqlite3.Row."""
    day = day or latest_activity_day(conn)
    empty = {
        "day": day,
        "has_activity": False,
        "runs": [],
        "totals": {"runs": 0, "accepted": 0, "rework": 0, "rollback": 0,
                   "needs_verdict": 0, "known_tokens": 0, "unknown_cost_runs": 0},
        "scored": {"cards": 0, "output_tokens": 0, "avg_score": None,
                   "total_cost": None},
        "rulings_applied": 0,
        "headline": "No runs to reflect on yet." if day is None
                    else f"No runs on {day}.",
    }
    if day is None:
        return empty

    run_rows = _rows(
        conn,
        "SELECT id, objective, task_class, model, human_acceptance, "
        "verification_outcome, artifact_manifest, cost_observation, opened_at "
        "FROM task_runs WHERE substr(opened_at,1,10)=? ORDER BY opened_at",
        (day,),
    )

    runs = []
    totals = {"runs": 0, "accepted": 0, "rework": 0, "rollback": 0,
              "needs_verdict": 0, "known_tokens": 0, "unknown_cost_runs": 0}
    for r in run_rows:
        try:
            n_artifacts = len(json.loads(r["artifact_manifest"] or "[]"))
        except (json.JSONDecodeError, TypeError):
            n_artifacts = 0
        acc = r["human_acceptance"]
        outcome = _OUTCOME.get(acc, "needs_verdict")
        tokens, known = _run_tokens(r["cost_observation"])
        runs.append({
            "id": r["id"],
            "objective": r["objective"],
            "model": r["model"] or "unknown",
            "provenance": _provenance(r["task_class"]),
            "outcome": outcome,
            "artifacts": n_artifacts,
            "verification": r["verification_outcome"] or "unverified",
            "tokens": tokens,
            "cost_status": "known" if known else "unknown",
        })
        totals["runs"] += 1
        if outcome == "needs_verdict":
            totals["needs_verdict"] += 1
        else:
            totals[outcome] += 1
        if known:
            totals["known_tokens"] += tokens
        else:
            totals["unknown_cost_runs"] += 1

    card_rows = _rows(
        conn,
        "SELECT output_tokens, score, cost, verified_ratio FROM run_cards "
        "WHERE substr(start,1,10)=?",
        (day,),
    )
    scores = [c["score"] for c in card_rows if c["score"] is not None]
    costs = [c["cost"] for c in card_rows if c["cost"] is not None]
    scored = {
        "cards": len(card_rows),
        "output_tokens": sum((c["output_tokens"] or 0) for c in card_rows),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
        "total_cost": round(sum(costs), 2) if costs else None,
    }

    rulings = _scalar(
        conn,
        "SELECT COUNT(*) FROM govern_batches "
        "WHERE undone_at IS NULL AND substr(applied_at,1,10)=?",
        (day,), default=0) or 0

    has_activity = bool(runs or card_rows or rulings)
    if not has_activity:
        return {**empty, "day": day}

    return {
        "day": day,
        "has_activity": True,
        "runs": runs,
        "totals": totals,
        "scored": scored,
        "rulings_applied": rulings,
        "headline": _headline(day, totals, scored, rulings),
    }


def _headline(day, totals, scored, rulings) -> str:
    """One plain sentence a tired human can read at 9am."""
    parts = []
    if totals["runs"]:
        parts.append(f"{totals['runs']} run{'' if totals['runs'] == 1 else 's'}")
        if totals["needs_verdict"]:
            parts.append(f"{totals['needs_verdict']} need your verdict")
        if totals["accepted"]:
            parts.append(f"{totals['accepted']} accepted")
    elif scored["cards"]:
        parts.append(f"{scored['cards']} run{'' if scored['cards'] == 1 else 's'} scored")
    if rulings:
        parts.append(f"{rulings} ruling{'' if rulings == 1 else 's'} applied")
    body = " · ".join(parts) if parts else "activity recorded"
    return f"Today ({day}): {body}."


def format_day_reflection(d: dict) -> str:
    """Human-readable CLI rendering — the day, honestly."""
    L = ["", f"  ── Reflection · {d['day'] or 'no activity'} "
             "─────────────────────────────"]
    if not d["has_activity"]:
        L.append(f"\n  {d['headline']}\n")
        return "\n".join(L)

    t = d["totals"]
    L.append(f"\n  {d['headline']}")
    L.append("")
    if t["runs"]:
        L.append(f"  runs         {t['runs']}  "
                 f"({t['accepted']} accepted · {t['rework']} rework · "
                 f"{t['rollback']} rejected · {t['needs_verdict']} need you)")
        tok = f"{t['known_tokens']:,} tokens" if t["known_tokens"] else "no known cost"
        unk = f" · {t['unknown_cost_runs']} unknown cost" if t["unknown_cost_runs"] else ""
        L.append(f"  cost         {tok}{unk}")
    s = d["scored"]
    if s["cards"]:
        avg = s["avg_score"] if s["avg_score"] is not None else "n/a"
        L.append(f"  scored       {s['cards']} card(s) · avg score {avg} · "
                 f"{s['output_tokens']:,} output tokens")
    if d["rulings_applied"]:
        L.append(f"  rulings      {d['rulings_applied']} applied")
    L.append("")
    for r in d["runs"][:12]:
        obj = (r["objective"] or "")[:52]
        L.append(f"    · [{r['outcome']:12}] {obj}  "
                 f"({r['model']}, {r['artifacts']} file(s))")
    L.append("")
    return "\n".join(L)
