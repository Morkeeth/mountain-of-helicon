"""Context Impact Tracking: close the loop between memory retrieval and output quality.

The question: "Did having this memory make the agent's output better?"
Answer: track what was surfaced (retrieval_log), what was produced after,
and whether the output was approved or killed.
"""

import sqlite3
from datetime import datetime


def compute_context_impact(conn: sqlite3.Connection) -> dict:
    """Analyze whether surfaced memories correlate with better outcomes."""
    surfaced = conn.execute(
        "SELECT cube_id, context, retrieved_at, was_acted_on FROM retrieval_log "
        "ORDER BY retrieved_at DESC"
    ).fetchall()

    if not surfaced:
        return {
            "total_retrievals": 0,
            "acted_on": 0,
            "impact_score": 0,
            "by_type": {},
            "top_useful": [],
            "top_ignored": [],
        }

    total = len(surfaced)
    acted = sum(1 for s in surfaced if s["was_acted_on"])

    by_type = {}
    for s in surfaced:
        cube = conn.execute(
            "SELECT type, title, review_status FROM glaze_cubes WHERE id = ?",
            (s["cube_id"],),
        ).fetchone()
        if not cube:
            continue

        t = cube["type"]
        if t not in by_type:
            by_type[t] = {"surfaced": 0, "acted_on": 0, "titles": []}
        by_type[t]["surfaced"] += 1
        if s["was_acted_on"]:
            by_type[t]["acted_on"] += 1
        by_type[t]["titles"].append(cube["title"][:40])

    cube_counts = {}
    for s in surfaced:
        cid = s["cube_id"]
        if cid not in cube_counts:
            cube_counts[cid] = {"surfaced": 0, "acted_on": 0}
        cube_counts[cid]["surfaced"] += 1
        if s["was_acted_on"]:
            cube_counts[cid]["acted_on"] += 1

    top_useful = []
    top_ignored = []
    for cid, counts in sorted(cube_counts.items(), key=lambda x: x[1]["surfaced"], reverse=True):
        cube = conn.execute(
            "SELECT title, type, confidence FROM glaze_cubes WHERE id = ?", (cid,)
        ).fetchone()
        if not cube:
            continue
        entry = {
            "cube_id": cid,
            "title": cube["title"][:50],
            "type": cube["type"],
            "surfaced": counts["surfaced"],
            "acted_on": counts["acted_on"],
            "hit_rate": round(counts["acted_on"] / counts["surfaced"], 2) if counts["surfaced"] > 0 else 0,
        }
        if counts["acted_on"] > 0:
            top_useful.append(entry)
        else:
            top_ignored.append(entry)

    return {
        "total_retrievals": total,
        "acted_on": acted,
        "impact_score": round(acted / total * 100, 1) if total > 0 else 0,
        "by_type": {k: {"surfaced": v["surfaced"], "acted_on": v["acted_on"]} for k, v in by_type.items()},
        "top_useful": sorted(top_useful, key=lambda x: x["hit_rate"], reverse=True)[:10],
        "top_ignored": top_ignored[:10],
    }


def link_review_to_context(conn: sqlite3.Connection, cube_id: str, decision: str):
    """After a review, mark related retrieval_log entries as acted_on."""
    if decision in ("approved", "revised"):
        conn.execute(
            "UPDATE retrieval_log SET was_acted_on = 1 "
            "WHERE cube_id = ? AND was_acted_on = 0",
            (cube_id,),
        )
        conn.commit()


def get_memory_usefulness(conn: sqlite3.Connection, cube_id: str) -> dict:
    """How useful has a specific memory been when surfaced?"""
    rows = conn.execute(
        "SELECT COUNT(*) as total, SUM(was_acted_on) as acted "
        "FROM retrieval_log WHERE cube_id = ?",
        (cube_id,),
    ).fetchone()

    total = rows["total"] or 0
    acted = rows["acted"] or 0

    return {
        "cube_id": cube_id,
        "times_surfaced": total,
        "times_acted_on": acted,
        "usefulness_score": round(acted / total * 100, 1) if total > 0 else None,
    }
