import json
import sqlite3
import uuid
from datetime import datetime

from glaze.models import Pattern
from glaze.qwen import complete_json


def make_id() -> str:
    return f"pat_{uuid.uuid4().hex[:10]}"


def detect_spin(conn: sqlite3.Connection, min_sessions: int = 4) -> list[dict]:
    rows = conn.execute(
        "SELECT tags, COUNT(DISTINCT source_ref) as session_count, "
        "COUNT(*) as cube_count, "
        "SUM(CASE WHEN review_status = 'pending' THEN 1 ELSE 0 END) as unreviewed "
        "FROM glaze_cubes WHERE merged_into IS NULL "
        "GROUP BY tags HAVING session_count >= ?",
        (min_sessions,),
    ).fetchall()

    spins = []
    for row in rows:
        tags = json.loads(row["tags"]) if row["tags"] else []
        tag_str = ", ".join(tags)
        if not tag_str or tag_str == "[]":
            continue
        spins.append({
            "tags": tags,
            "session_count": row["session_count"],
            "cube_count": row["cube_count"],
            "unreviewed": row["unreviewed"],
            "spin_score": row["session_count"] / max(row["cube_count"] - row["unreviewed"], 1),
        })

    return sorted(spins, key=lambda x: x["spin_score"], reverse=True)[:20]


def detect_kill_candidates(conn: sqlite3.Connection, days_threshold: int = 30) -> list[dict]:
    now = datetime.utcnow().isoformat()
    rows = conn.execute(
        "SELECT id, title, type, confidence, created_at, source "
        "FROM glaze_cubes "
        "WHERE review_status = 'pending' AND confidence < 0.1 AND merged_into IS NULL "
        "ORDER BY confidence ASC LIMIT 20"
    ).fetchall()

    candidates = []
    for row in rows:
        try:
            clean = row["created_at"].replace("Z", "")
            if "+" in clean:
                clean = clean.split("+")[0]
            created = datetime.fromisoformat(clean)
            age_days = (datetime.utcnow() - created).total_seconds() / 86400
        except (ValueError, AttributeError):
            age_days = 0

        candidates.append({
            "id": row["id"],
            "title": row["title"],
            "type": row["type"],
            "confidence": row["confidence"],
            "age_days": round(age_days, 1),
            "source": row["source"],
        })

    return candidates


def compute_velocity(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT cube_type, "
        "AVG(time_to_review_seconds) as avg_time, "
        "AVG(cube_age_days) as avg_age, "
        "COUNT(*) as cnt "
        "FROM reviews GROUP BY cube_type"
    ).fetchall()

    velocity = {}
    for row in rows:
        if row["cube_type"]:
            velocity[row["cube_type"]] = {
                "avg_review_time_seconds": round(row["avg_time"], 1),
                "avg_age_at_review_days": round(row["avg_age"], 1),
                "review_count": row["cnt"],
            }
    return velocity


def compute_shipping_rates(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT type, "
        "COUNT(*) as total, "
        "SUM(CASE WHEN review_status = 'approved' THEN 1 ELSE 0 END) as approved, "
        "SUM(CASE WHEN review_status = 'killed' THEN 1 ELSE 0 END) as killed, "
        "SUM(CASE WHEN review_status = 'revised' THEN 1 ELSE 0 END) as revised, "
        "SUM(CASE WHEN review_status = 'pending' THEN 1 ELSE 0 END) as pending "
        "FROM glaze_cubes WHERE merged_into IS NULL GROUP BY type"
    ).fetchall()

    rates = {}
    for row in rows:
        total = row["total"]
        rates[row["type"]] = {
            "total": total,
            "approved": row["approved"],
            "killed": row["killed"],
            "revised": row["revised"],
            "pending": row["pending"],
            "ship_rate": round(row["approved"] / total * 100, 1) if total > 0 else 0,
            "kill_rate": round(row["killed"] / total * 100, 1) if total > 0 else 0,
        }
    return rates


def extract_patterns_with_qwen(conn: sqlite3.Connection, qwen_client) -> list[Pattern]:
    if qwen_client is None:
        return extract_patterns_from_sql(conn)

    reviews = conn.execute(
        "SELECT cube_type, decision, cube_age_days, time_to_review_seconds, cube_source "
        "FROM reviews ORDER BY reviewed_at DESC LIMIT 50"
    ).fetchall()

    if len(reviews) < 5:
        return extract_patterns_from_sql(conn)

    review_text = "\n".join(
        f"- {r['cube_type']} from {r['cube_source']}: {r['decision']} after {r['cube_age_days']:.0f} days"
        for r in reviews
    )

    result = complete_json(
        qwen_client,
        "You are a behavioral pattern detector for a memory audit system.",
        f"""Analyze these review decisions and extract behavioral patterns.

Review history:
{review_text}

Return JSON array of patterns:
[{{
  "name": "short pattern name",
  "description": "what the pattern says about the reviewer's behavior",
  "pattern_type": "velocity | shipping | decay | spin | kill_prediction",
  "confidence": 0.0-1.0
}}]""",
    )

    if not result or not isinstance(result, list):
        return extract_patterns_from_sql(conn)

    now = datetime.utcnow().isoformat()
    patterns = []
    for item in result:
        patterns.append(Pattern(
            id=make_id(),
            name=item.get("name", "unnamed"),
            description=item.get("description", ""),
            pattern_type=item.get("pattern_type", "custom"),
            data_points=len(reviews),
            confidence=item.get("confidence", 0.5),
            last_reinforced=now,
            created_at=now,
            updated_at=now,
            evidence=[r["cube_type"] for r in reviews[:10]],
            status="active",
        ))

    return patterns


def extract_patterns_from_sql(conn: sqlite3.Connection) -> list[Pattern]:
    now = datetime.utcnow().isoformat()
    patterns = []

    velocity = compute_velocity(conn)
    for cube_type, stats in velocity.items():
        patterns.append(Pattern(
            id=make_id(),
            name=f"{cube_type} review velocity",
            description=f"You review {cube_type} items in avg {stats['avg_age_at_review_days']:.0f} days",
            pattern_type="velocity",
            data_points=stats["review_count"],
            confidence=min(stats["review_count"] / 10, 1.0),
            last_reinforced=now,
            created_at=now,
            updated_at=now,
            status="active",
        ))

    rates = compute_shipping_rates(conn)
    for cube_type, stats in rates.items():
        if stats["kill_rate"] > 50 and stats["total"] >= 3:
            patterns.append(Pattern(
                id=make_id(),
                name=f"{cube_type} kill pattern",
                description=f"{stats['kill_rate']:.0f}% of {cube_type} items get killed ({stats['killed']}/{stats['total']})",
                pattern_type="kill_prediction",
                data_points=stats["total"],
                confidence=min(stats["total"] / 10, 1.0),
                last_reinforced=now,
                created_at=now,
                updated_at=now,
                status="active",
            ))

    return patterns


def save_patterns(conn: sqlite3.Connection, patterns: list[Pattern]):
    for p in patterns:
        conn.execute(
            """INSERT OR REPLACE INTO patterns
            (id, name, description, pattern_type, data_points, confidence,
             last_reinforced, last_challenged, created_at, updated_at, evidence, status, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                p.id, p.name, p.description, p.pattern_type, p.data_points,
                p.confidence, p.last_reinforced, p.last_challenged,
                p.created_at, p.updated_at, json.dumps(p.evidence),
                p.status, json.dumps(p.metadata),
            ),
        )
    conn.commit()
