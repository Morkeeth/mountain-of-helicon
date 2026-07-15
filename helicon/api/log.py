"""Log API — the LOG surface of the dashboard: receipts of what Helicon DID.

Merges the system's real action trails into one newest-first feed:

  - audit_log: every finding Helicon flagged (actor 'qwen' when the factual
    contradiction judge produced it, 'helicon' otherwise), plus the human's
    resolution when one was recorded
  - reviews: human decisions (kept / killed / revised, with notes); auto-triage
    review rows are excluded here because triage_log below is their receipt
  - triage_log: autonomous kill/approve calls made from learned rules
  - superseded cubes: reconciliation batches — cubes a re-scan retired, grouped
    per source per day (helicon_cubes has no supersede timestamp, so the best
    available timestamp — last_reinforced, else created_at — dates the batch)

Every row: {ts, actor ('human'|'helicon'|'qwen'), action, detail, count?}.
"""
from fastapi import APIRouter

from helicon.api.app import get_conn

router = APIRouter()

# reviews.decision -> the verb the dashboard speaks
_DECISION_VERB = {"approved": "kept", "killed": "killed", "revised": "revised"}


def _audit_entries(conn, limit: int) -> list[dict]:
    rows = conn.execute(
        """SELECT id, audit_type, target_id, finding, severity,
                  human_decision, audited_at, resolved_at
           FROM audit_log ORDER BY audited_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    entries = []
    for r in rows:
        entries.append({
            "ts": r["audited_at"],
            "actor": "qwen" if r["audit_type"] == "factual" else "helicon",
            "action": f"audit_flag_{r['audit_type']}",
            "detail": f"[{r['severity']}] {r['finding']}",
        })
        if r["human_decision"]:
            entries.append({
                "ts": r["resolved_at"] or r["audited_at"],
                "actor": "human",
                "action": f"audit_{r['human_decision']}",
                "detail": r["finding"],
            })
    return entries


def _review_entries(conn, limit: int) -> list[dict]:
    from helicon.db import human_evidence_sql
    rows = conn.execute(
        f"""SELECT r.decision, r.notes, r.reviewed_at, r.cube_id, c.title
           FROM reviews r LEFT JOIN helicon_cubes c ON c.id = r.cube_id
           WHERE {human_evidence_sql("r.")}
           ORDER BY r.reviewed_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    entries = []
    for r in rows:
        verb = _DECISION_VERB.get(r["decision"], r["decision"])
        detail = f"{verb} '{r['title'] or r['cube_id']}'"
        if r["notes"]:
            detail += f": {r['notes']}"
        entries.append({
            "ts": r["reviewed_at"],
            "actor": "human",
            "action": f"review_{verb}",
            "detail": detail,
        })
    return entries


def _triage_entries(conn, limit: int) -> list[dict]:
    try:
        rows = conn.execute(
            """SELECT t.cube_id, t.action, t.reason, t.rule_confidence,
                      t.triaged_at, c.title
               FROM triage_log t LEFT JOIN helicon_cubes c ON c.id = t.cube_id
               ORDER BY t.triaged_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    except Exception:
        return []  # triage_log not initialised in this DB
    return [{
        "ts": r["triaged_at"],
        "actor": "helicon",
        "action": f"triage_{r['action']}",
        "detail": (f"{r['action']} '{r['title'] or r['cube_id']}': {r['reason']} "
                   f"(rule confidence {r['rule_confidence']:.0%})"),
    } for r in rows]


def _superseded_entries(conn, limit: int) -> list[dict]:
    rows = conn.execute(
        """SELECT source,
                  substr(COALESCE(NULLIF(last_reinforced, ''), created_at), 1, 10) AS day,
                  MAX(COALESCE(NULLIF(last_reinforced, ''), created_at)) AS ts,
                  COUNT(*) AS n
           FROM helicon_cubes
           WHERE review_status = 'superseded'
           GROUP BY source, day
           ORDER BY ts DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [{
        "ts": r["ts"],
        "actor": "helicon",
        "action": "reconcile_superseded",
        "detail": (f"retired {r['n']} stale memories from {r['source']} "
                   f"(re-scan no longer sees their content)"),
        "count": r["n"],
    } for r in rows]


@router.get("/log")
async def get_log(limit: int = 50):
    """Newest-first receipts of what Helicon (and the human) did. ?limit= caps
    the merged feed (default 50); each source is pre-capped at the same limit."""
    conn = get_conn()
    limit = max(limit, 0)

    entries = []
    entries.extend(_audit_entries(conn, limit))
    entries.extend(_review_entries(conn, limit))
    entries.extend(_triage_entries(conn, limit))
    entries.extend(_superseded_entries(conn, limit))

    entries.sort(key=lambda e: e["ts"] or "", reverse=True)
    entries = entries[:limit]

    return {"entries": entries, "total": len(entries)}
