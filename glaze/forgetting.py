import math
import sqlite3
from datetime import datetime

DEFAULT_STABILITY = {
    "code": 7.0,
    "file_created": 14.0,
    "decision": 30.0,
    "draft": 10.0,
    "pattern": 60.0,
    "memory": 45.0,
    "session": 90.0,
    "project": 30.0,
    "dashboard": 7.0,
    "idea": 21.0,
    "archive": 180.0,
    "personal": 90.0,
}

DEFAULT_SHAPE = {
    "code": 1.5,
    "file_created": 1.2,
    "decision": 0.8,
    "draft": 1.8,
    "pattern": 0.7,
    "memory": 0.9,
    "session": 0.6,
    "project": 1.0,
    "dashboard": 2.0,
    "idea": 1.3,
    "archive": 0.5,
    "personal": 0.7,
}


def weibull_decay(
    days_since_reinforcement: float,
    eta: float = 14.0,
    kappa: float = 1.0,
    review_count: int = 0,
) -> float:
    """Weibull decay: w(Δτ) = exp(-(Δτ/η)^κ)

    From SSGM Framework (2026) via Huang et al. LiCoMemory.
    κ < 1: slow initial decay, accelerates later (good for decisions, patterns)
    κ = 1: exponential (equivalent to Ebbinghaus)
    κ > 1: fast initial decay, slows later (good for code, dashboards)
    """
    effective_eta = eta * (1 + 0.5 * review_count)
    if effective_eta <= 0:
        return 0.0
    return math.exp(-((days_since_reinforcement / effective_eta) ** kappa))


def ebbinghaus_decay(
    days_since_reinforcement: float,
    stability: float = 14.0,
    review_count: int = 0,
) -> float:
    effective_stability = stability * (1 + 0.5 * review_count)
    if effective_stability <= 0:
        return 0.0
    return math.exp(-days_since_reinforcement / effective_stability)


def apply_decay(conn: sqlite3.Connection, config: dict | None = None) -> dict:
    stability_overrides = {}
    if config:
        stability_overrides = config.get("forgetting", {}).get("stability", {})

    now = datetime.utcnow()
    cursor = conn.execute(
        "SELECT id, confidence, last_reinforced, created_at, type, review_count "
        "FROM glaze_cubes WHERE review_status IN ('pending', 'revised')"
    )

    updated = 0
    critical = 0
    decayed_items = []

    for row in cursor.fetchall():
        cube_id = row["id"]
        cube_type = row["type"]
        review_count = row["review_count"]
        last_reinforced = row["last_reinforced"] or row["created_at"]

        try:
            clean = last_reinforced.replace("Z", "")
            if "+" in clean:
                clean = clean.split("+")[0]
            last_dt = datetime.fromisoformat(clean)
        except (ValueError, AttributeError):
            continue

        days = (now - last_dt).total_seconds() / 86400
        if days < 0:
            days = 0

        stability = stability_overrides.get(cube_type, DEFAULT_STABILITY.get(cube_type, 14.0))
        shape = DEFAULT_SHAPE.get(cube_type, 1.0)
        new_conf = round(weibull_decay(days, stability, shape, review_count), 4)
        old_conf = row["confidence"]

        if abs(new_conf - old_conf) > 0.005:
            conn.execute(
                "UPDATE glaze_cubes SET confidence = ? WHERE id = ?",
                (new_conf, cube_id),
            )
            updated += 1

            if new_conf < 0.05:
                critical += 1
                decayed_items.append({
                    "id": cube_id,
                    "type": cube_type,
                    "confidence": new_conf,
                    "days_old": round(days, 1),
                })

    conn.commit()

    return {
        "updated": updated,
        "critical_decay": critical,
        "most_decayed": sorted(decayed_items, key=lambda x: x["confidence"])[:20],
    }


def get_decay_stats(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT type, AVG(confidence) as avg_conf, MIN(confidence) as min_conf, "
        "COUNT(*) as cnt FROM glaze_cubes WHERE review_status = 'pending' GROUP BY type"
    ).fetchall()

    stats = {}
    for row in rows:
        cube_type = row["type"]
        stats[cube_type] = {
            "avg_confidence": round(row["avg_conf"], 3),
            "min_confidence": round(row["min_conf"], 4),
            "count": row["cnt"],
            "eta": DEFAULT_STABILITY.get(cube_type, 14.0),
            "kappa": DEFAULT_SHAPE.get(cube_type, 1.0),
            "decay_model": "weibull",
        }
    return stats
