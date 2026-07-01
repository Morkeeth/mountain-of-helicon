import json
import sqlite3
from datetime import datetime, timedelta

from glaze.qwen import complete_json, resolve_model


def detect_session(conn: sqlite3.Connection, window_minutes: int = 60) -> dict | None:
    """Detect if there's a recent review session worth summarizing."""
    cutoff = (datetime.utcnow() - timedelta(minutes=window_minutes)).isoformat()
    rows = conn.execute(
        "SELECT r.*, g.title, g.tags FROM reviews r "
        "JOIN glaze_cubes g ON r.cube_id = g.id "
        "WHERE r.reviewed_at > ? ORDER BY r.reviewed_at DESC",
        (cutoff,),
    ).fetchall()

    if len(rows) < 3:
        return None

    decisions = {}
    types_reviewed = {}
    sources_reviewed = {}
    for r in rows:
        d = r["decision"]
        decisions[d] = decisions.get(d, 0) + 1
        t = r["cube_type"]
        types_reviewed[t] = types_reviewed.get(t, 0) + 1
        s = r["cube_source"]
        sources_reviewed[s] = sources_reviewed.get(s, 0) + 1

    return {
        "review_count": len(rows),
        "decisions": decisions,
        "types_reviewed": types_reviewed,
        "sources_reviewed": sources_reviewed,
        "reviews": [dict(r) for r in rows],
        "window_start": rows[-1]["reviewed_at"],
        "window_end": rows[0]["reviewed_at"],
    }


def generate_session_summary(
    conn: sqlite3.Connection, qwen_client=None, config: dict | None = None
) -> dict | None:
    """Generate a structured audit summary for the current review session."""
    session = detect_session(conn)
    if not session:
        return None

    killed_titles = [
        r["title"] for r in session["reviews"] if r["decision"] == "killed"
    ]
    approved_titles = [
        r["title"] for r in session["reviews"] if r["decision"] == "approved"
    ]
    revised_titles = [
        r["title"] for r in session["reviews"] if r["decision"] == "revised"
    ]

    summary = {
        "session_start": session["window_start"],
        "session_end": session["window_end"],
        "total_reviews": session["review_count"],
        "decisions": session["decisions"],
        "types_reviewed": session["types_reviewed"],
        "sources_reviewed": session["sources_reviewed"],
        "killed": killed_titles[:10],
        "approved": approved_titles[:10],
        "revised": revised_titles[:10],
        "kill_rate": round(
            session["decisions"].get("killed", 0) / max(session["review_count"], 1), 3
        ),
    }

    if qwen_client and session["review_count"] >= 5:
        model = resolve_model("default", config)
        review_data = json.dumps(
            {
                "decisions": session["decisions"],
                "types": session["types_reviewed"],
                "killed": killed_titles[:5],
                "approved": approved_titles[:5],
            }
        )
        insights = complete_json(
            qwen_client,
            "You are a memory audit analyst. Given a review session summary, extract behavioral insights.",
            f"""This user just reviewed {session['review_count']} memory items. Analyze their behavior:

{review_data}

Return JSON:
{{
  "behavior_insight": "one sentence about what this session reveals about the user's review style",
  "emerging_pattern": "any new pattern visible (e.g. killing all content items, approving only code)",
  "drift_signal": "does this session differ from what you'd expect? describe how",
  "recommended_next": "what should be surfaced next based on this session"
}}""",
            model,
            operation="session_summary",
        )
        if insights:
            summary["insights"] = insights

    _store_session_summary(conn, summary)
    return summary


def _store_session_summary(conn: sqlite3.Connection, summary: dict):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS session_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_start TEXT NOT NULL,
            session_end TEXT NOT NULL,
            total_reviews INTEGER NOT NULL,
            kill_rate REAL NOT NULL,
            decisions TEXT NOT NULL,
            types_reviewed TEXT NOT NULL,
            sources_reviewed TEXT NOT NULL,
            insights TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        "INSERT INTO session_summaries (session_start, session_end, total_reviews, kill_rate, decisions, types_reviewed, sources_reviewed, insights, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            summary["session_start"],
            summary["session_end"],
            summary["total_reviews"],
            summary["kill_rate"],
            json.dumps(summary["decisions"]),
            json.dumps(summary["types_reviewed"]),
            json.dumps(summary["sources_reviewed"]),
            json.dumps(summary.get("insights", {})),
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()


def get_session_summaries(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT * FROM session_summaries ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    except Exception:
        return []
    results = []
    for r in rows:
        d = dict(r)
        d["decisions"] = json.loads(d["decisions"]) if d["decisions"] else {}
        d["types_reviewed"] = json.loads(d["types_reviewed"]) if d["types_reviewed"] else {}
        d["sources_reviewed"] = json.loads(d["sources_reviewed"]) if d["sources_reviewed"] else {}
        d["insights"] = json.loads(d["insights"]) if d["insights"] else {}
        results.append(d)
    return results


def get_review_drift(conn: sqlite3.Connection) -> dict:
    """Detect drift in review behavior over time."""
    try:
        rows = conn.execute(
            "SELECT * FROM session_summaries ORDER BY created_at ASC"
        ).fetchall()
    except Exception:
        return {"sessions": 0, "drift_detected": False}

    if len(rows) < 2:
        return {"sessions": len(rows), "drift_detected": False}

    kill_rates = [r["kill_rate"] for r in rows]
    recent_rate = kill_rates[-1] if kill_rates else 0
    historical_avg = sum(kill_rates[:-1]) / max(len(kill_rates) - 1, 1)
    drift_magnitude = abs(recent_rate - historical_avg)

    type_evolution = []
    for r in rows:
        types = json.loads(r["types_reviewed"]) if r["types_reviewed"] else {}
        type_evolution.append(types)

    recent_types = set(type_evolution[-1].keys()) if type_evolution else set()
    early_types = set(type_evolution[0].keys()) if type_evolution else set()
    new_types = recent_types - early_types
    dropped_types = early_types - recent_types

    return {
        "sessions": len(rows),
        "drift_detected": drift_magnitude > 0.15,
        "kill_rate_trend": {
            "current": round(recent_rate, 3),
            "historical_avg": round(historical_avg, 3),
            "drift_magnitude": round(drift_magnitude, 3),
            "direction": "more aggressive" if recent_rate > historical_avg else "more lenient",
        },
        "type_evolution": {
            "new_types_reviewed": list(new_types),
            "dropped_types": list(dropped_types),
        },
        "session_history": [
            {
                "date": r["session_start"][:10],
                "reviews": r["total_reviews"],
                "kill_rate": r["kill_rate"],
            }
            for r in rows
        ],
    }
