import json
import sqlite3
from datetime import datetime


def init_score_history(conn: sqlite3.Connection):
    conn.execute("""CREATE TABLE IF NOT EXISTS score_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recorded_at TEXT NOT NULL,
        score REAL NOT NULL,
        total INTEGER NOT NULL,
        reviewed INTEGER NOT NULL,
        event_label TEXT,
        details TEXT
    )""")
    conn.commit()


def record_score_snapshot(conn: sqlite3.Connection, event_label: str = None):
    """Record current score as a point in time. Call after significant events."""
    init_score_history(conn)
    score = compute_score(conn)
    conn.execute(
        "INSERT INTO score_history (recorded_at, score, total, reviewed, event_label, details) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), score["score"], score["total"],
         score["reviewed"], event_label,
         json.dumps({"by_source": score["by_source"]})),
    )
    conn.commit()


def backfill_score_history(conn: sqlite3.Connection):
    """Reconstruct score timeline from existing review + triage timestamps."""
    init_score_history(conn)

    existing = conn.execute("SELECT COUNT(*) FROM score_history").fetchone()[0]
    if existing > 0:
        return {"status": "already_backfilled", "points": existing}

    total = conn.execute(
        "SELECT COUNT(*) FROM glaze_cubes WHERE merged_into IS NULL"
    ).fetchone()[0]
    if total == 0:
        return {"status": "no_data", "points": 0}

    first_scan = conn.execute(
        "SELECT MIN(created_at) FROM glaze_cubes"
    ).fetchone()[0]
    if first_scan:
        conn.execute(
            "INSERT INTO score_history (recorded_at, score, total, reviewed, event_label) "
            "VALUES (?, 0, ?, 0, ?)",
            (first_scan, total, f"First scan: {total} cubes ingested"),
        )

    human_reviews = conn.execute(
        "SELECT MIN(reviewed_at) as last_at, COUNT(*) as cnt "
        "FROM reviews WHERE session_id != 'auto-triage'"
    ).fetchone()

    behavioral_triage = conn.execute(
        "SELECT MIN(triaged_at) as first_at, COUNT(*) as cnt "
        "FROM triage_log WHERE reason LIKE '%historically%'"
    ).fetchone()

    decay_triage = conn.execute(
        "SELECT MIN(triaged_at) as first_at, COUNT(*) as cnt "
        "FROM triage_log WHERE reason LIKE '%Weibull%'"
    ).fetchone()

    events = []

    if human_reviews and human_reviews["cnt"] > 0:
        events.append({
            "ts": human_reviews["last_at"],
            "reviewed": human_reviews["cnt"],
            "label": f"{human_reviews['cnt']} human reviews completed",
        })

    if behavioral_triage and behavioral_triage["cnt"] > 0:
        prev = sum(e["reviewed"] for e in events)
        events.append({
            "ts": behavioral_triage["first_at"],
            "reviewed": prev + behavioral_triage["cnt"],
            "label": f"Auto-triage: {behavioral_triage['cnt']} items (behavioral rules)",
        })

    if decay_triage and decay_triage["cnt"] > 0:
        all_reviewed = conn.execute(
            "SELECT COUNT(*) FROM glaze_cubes "
            "WHERE review_status IN ('approved','revised','killed') AND merged_into IS NULL"
        ).fetchone()[0]
        events.append({
            "ts": decay_triage["first_at"],
            "reviewed": all_reviewed,
            "label": f"Decay-based triage: {decay_triage['cnt']} more items",
        })

    events.sort(key=lambda e: e["ts"])

    for e in events:
        score_val = round((e["reviewed"] / total) * 100, 1)
        conn.execute(
            "INSERT INTO score_history (recorded_at, score, total, reviewed, event_label) "
            "VALUES (?, ?, ?, ?, ?)",
            (e["ts"], score_val, total, e["reviewed"], e["label"]),
        )

    conn.commit()
    points = conn.execute("SELECT COUNT(*) FROM score_history").fetchone()[0]
    return {"status": "backfilled", "points": points}


def get_score_history(conn: sqlite3.Connection) -> list[dict]:
    init_score_history(conn)
    rows = conn.execute(
        "SELECT id, recorded_at, score, total, reviewed, event_label "
        "FROM score_history ORDER BY recorded_at ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def compute_score(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM glaze_cubes WHERE merged_into IS NULL").fetchone()[0]
    if total == 0:
        return {"score": 0, "total": 0, "reviewed": 0, "breakdown": {}}

    reviewed = conn.execute(
        "SELECT COUNT(*) FROM glaze_cubes WHERE review_status IN ('approved', 'revised', 'killed') AND merged_into IS NULL"
    ).fetchone()[0]

    score = round((reviewed / total) * 100, 1) if total > 0 else 0

    by_source = {}
    rows = conn.execute(
        "SELECT source, "
        "COUNT(*) as total, "
        "SUM(CASE WHEN review_status IN ('approved','revised','killed') THEN 1 ELSE 0 END) as reviewed "
        "FROM glaze_cubes WHERE merged_into IS NULL GROUP BY source"
    ).fetchall()
    for row in rows:
        src_total = row["total"]
        src_reviewed = row["reviewed"]
        by_source[row["source"]] = {
            "total": src_total,
            "reviewed": src_reviewed,
            "score": round((src_reviewed / src_total) * 100, 1) if src_total > 0 else 0,
        }

    by_type = {}
    rows = conn.execute(
        "SELECT type, "
        "COUNT(*) as total, "
        "SUM(CASE WHEN review_status IN ('approved','revised','killed') THEN 1 ELSE 0 END) as reviewed "
        "FROM glaze_cubes WHERE merged_into IS NULL GROUP BY type"
    ).fetchall()
    for row in rows:
        t_total = row["total"]
        t_reviewed = row["reviewed"]
        by_type[row["type"]] = {
            "total": t_total,
            "reviewed": t_reviewed,
            "score": round((t_reviewed / t_total) * 100, 1) if t_total > 0 else 0,
        }

    by_decision = {}
    rows = conn.execute(
        "SELECT review_status, COUNT(*) as cnt FROM glaze_cubes WHERE merged_into IS NULL GROUP BY review_status"
    ).fetchall()
    for row in rows:
        by_decision[row["review_status"]] = row["cnt"]

    return {
        "score": score,
        "total": total,
        "reviewed": reviewed,
        "pending": total - reviewed,
        "by_source": by_source,
        "by_type": by_type,
        "by_decision": by_decision,
    }
