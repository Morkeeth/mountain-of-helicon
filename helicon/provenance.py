"""Memory Causal Lens — the memories behind an answer.

Given a task or an answer, show which memories the agent retrieved to produce it,
each with its provenance: source, age, confidence, review status, rank, and whether
a human ever acted on it when it surfaced. This is the read side of "a verdict,
remembered": you can see WHY the agent said what it said, and — the point — which
memory to correct upstream instead of editing the output.
"""
from datetime import datetime, timezone


def memory_provenance(conn, task: str, k: int = 8) -> list[dict]:
    """The ranked memories behind a task's answer, each annotated with provenance."""
    from helicon.snapshots import _retrieve
    hits = _retrieve(conn, task, k)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    out = []
    for rank, h in enumerate(hits, 1):
        cid = h.get("id")
        row = conn.execute(
            "SELECT source, source_ref, created_at, confidence, review_status "
            "FROM helicon_cubes WHERE id = ?", (cid,)).fetchone()
        if row is None:
            continue
        created = row["created_at"] or ""
        try:
            cdt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if cdt.tzinfo is not None:
                cdt = cdt.astimezone(timezone.utc).replace(tzinfo=None)
            age_days = (now - cdt).days
        except (ValueError, TypeError):
            age_days = None
        acted = conn.execute(
            "SELECT MAX(was_acted_on) FROM retrieval_log WHERE cube_id = ?",
            (cid,)).fetchone()
        out.append({
            "rank": rank,
            "id": cid,
            "title": h.get("title") or "",
            "source": row["source"] or "",
            "age_days": age_days,
            "confidence": round(row["confidence"] or 0, 3),
            "status": row["review_status"] or "",
            "acted_on": bool(acted and acted[0]),
        })
    return out


def format_provenance(task: str, rows: list[dict]) -> str:
    """Terminal rendering of the causal lens."""
    if not rows:
        return f'No memory stands behind "{task}".'
    lines = [f'The memories behind "{task}":', ""]
    for r in rows:
        age = f"{r['age_days']}d" if r["age_days"] is not None else "  ?"
        flags = []
        if r["age_days"] is not None and r["age_days"] > 90:
            flags.append("STALE")
        if r["status"] not in ("approved", "pending", ""):
            flags.append(r["status"])
        if r["acted_on"]:
            flags.append("acted-on")
        flag = f"   [{', '.join(flags)}]" if flags else ""
        lines.append(
            f"  {r['rank']}. {r['title'][:50]:<50} {r['source']:<11} "
            f"{age:>5}  conf {r['confidence']:<5}{flag}")
    lines += ["", "  correct upstream: retire a stale/wrong memory with  helicon resolve"]
    return "\n".join(lines)
