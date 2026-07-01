"""Auto-triage engine: GLAZE makes its own decisions based on learned patterns.

When pattern confidence is high enough, auto-approve or auto-kill without
human review. The human only sees uncertain items. This is what makes GLAZE
an agent, not just a tool.
"""

import json
import sqlite3
from datetime import datetime


def _get_type_kill_rates(conn: sqlite3.Connection) -> dict[str, dict]:
    # Only learn from HUMAN reviews. Including auto-triage's own kills would let
    # the engine read back its own past decisions as "evidence" and reinforce
    # them - a feedback echo, not learning. (Audit found ~88% of the old "code"
    # rule evidence was self-generated.)
    rows = conn.execute(
        "SELECT cube_type, decision, COUNT(*) as cnt "
        "FROM reviews WHERE session_id != 'auto-triage' "
        "GROUP BY cube_type, decision"
    ).fetchall()

    by_type: dict[str, dict] = {}
    for r in rows:
        t = r["cube_type"] or "unknown"
        if t not in by_type:
            by_type[t] = {"total": 0, "killed": 0, "approved": 0, "revised": 0}
        by_type[t]["total"] += r["cnt"]
        by_type[t][r["decision"]] = r["cnt"]

    for t in by_type:
        total = by_type[t]["total"]
        by_type[t]["kill_rate"] = by_type[t]["killed"] / total if total > 0 else 0
        by_type[t]["approve_rate"] = by_type[t]["approved"] / total if total > 0 else 0

    return by_type


def _get_source_kill_rates(conn: sqlite3.Connection) -> dict[str, dict]:
    # Human reviews only - see _get_type_kill_rates. Auto-triage rows excluded so
    # the engine doesn't grade its own decisions.
    rows = conn.execute(
        "SELECT cube_source, decision, COUNT(*) as cnt "
        "FROM reviews WHERE session_id != 'auto-triage' "
        "GROUP BY cube_source, decision"
    ).fetchall()

    by_source: dict[str, dict] = {}
    for r in rows:
        s = r["cube_source"] or "unknown"
        if s not in by_source:
            by_source[s] = {"total": 0, "killed": 0, "approved": 0}
        by_source[s]["total"] += r["cnt"]
        by_source[s][r["decision"]] = by_source[s].get(r["decision"], 0) + r["cnt"]

    for s in by_source:
        total = by_source[s]["total"]
        by_source[s]["kill_rate"] = by_source[s]["killed"] / total if total > 0 else 0

    return by_source


def compute_triage_rules(conn: sqlite3.Connection) -> list[dict]:
    """Derive auto-triage rules from review history + decay-based fallbacks."""
    type_rates = _get_type_kill_rates(conn)
    rules = []

    for cube_type, stats in type_rates.items():
        if stats["total"] < 5:
            continue

        if stats["kill_rate"] >= 0.95 and stats["total"] >= 20:
            rules.append({
                "action": "kill",
                "condition": f"type={cube_type} AND confidence<0.60",
                "cube_type": cube_type,
                "confidence_threshold": 0.60,
                "rule_confidence": min(stats["total"] / 20, 1.0),
                "evidence": f"{stats['killed']}/{stats['total']} killed historically ({stats['kill_rate']:.0%})",
                "rule_type": "behavioral",
            })
        elif stats["kill_rate"] >= 0.75:
            rules.append({
                "action": "kill",
                "condition": f"type={cube_type} AND confidence<0.10",
                "cube_type": cube_type,
                "confidence_threshold": 0.10,
                "rule_confidence": min(stats["total"] / 20, 1.0),
                "evidence": f"{stats['killed']}/{stats['total']} killed historically ({stats['kill_rate']:.0%})",
                "rule_type": "behavioral",
            })

        if stats["approve_rate"] >= 0.80 and stats["total"] >= 8:
            rules.append({
                "action": "approve",
                "condition": f"type={cube_type} AND confidence>0.60",
                "cube_type": cube_type,
                "confidence_threshold": 0.60,
                "rule_confidence": min(stats["total"] / 20, 1.0),
                "evidence": f"{stats['approved']}/{stats['total']} approved historically ({stats['approve_rate']:.0%})",
                "rule_type": "behavioral",
            })

    rules.extend(_decay_based_rules(conn, type_rates))
    rules.extend(_confidence_floor_rules(conn))
    return rules


def _confidence_floor_rules(conn: sqlite3.Connection) -> list[dict]:
    """Kill items below 20% confidence regardless of type. If Weibull decay
    has dropped confidence this low, the item is stale by definition."""
    count = conn.execute(
        "SELECT COUNT(*) FROM glaze_cubes "
        "WHERE review_status = 'pending' AND merged_into IS NULL AND confidence < 0.20"
    ).fetchone()[0]

    rules = []
    if count >= 3:
        rules.append({
            "action": "kill",
            "condition": "confidence<0.20",
            "cube_type": None,
            "confidence_threshold": 0.20,
            "rule_confidence": 0.85,
            "evidence": f"{count} items below 20% confidence (Weibull decay floor)",
            "rule_type": "decay-floor",
        })

    zero_review_types = conn.execute(
        "SELECT type, COUNT(*) as cnt FROM glaze_cubes "
        "WHERE review_status = 'pending' AND merged_into IS NULL "
        "AND type NOT IN (SELECT DISTINCT cube_type FROM reviews WHERE cube_type IS NOT NULL) "
        "GROUP BY type HAVING cnt >= 3"
    ).fetchall()

    for row in zero_review_types:
        rules.append({
            "action": "kill",
            "condition": f"type={row['type']} AND confidence<0.70",
            "cube_type": row["type"],
            "confidence_threshold": 0.70,
            "rule_confidence": 0.7,
            "evidence": f"{row['cnt']} {row['type']} items with zero human reviews (unreviewed type)",
            "rule_type": "unreviewed-type",
        })

    return rules


def _decay_based_rules(conn: sqlite3.Connection, type_rates: dict) -> list[dict]:
    """Weibull-based triage for types without enough review history.
    If confidence has decayed below 5%, the Weibull model itself is the evidence."""
    reviewed_types = {t for t, s in type_rates.items() if s["total"] >= 5}

    pending_by_type = conn.execute(
        "SELECT type, COUNT(*) as cnt, AVG(confidence) as avg_conf, "
        "MIN(confidence) as min_conf "
        "FROM glaze_cubes WHERE review_status = 'pending' AND merged_into IS NULL "
        "GROUP BY type"
    ).fetchall()

    rules = []
    for row in pending_by_type:
        cube_type = row["type"]
        if cube_type in reviewed_types:
            continue
        if row["cnt"] < 3:
            continue

        low_conf_count = conn.execute(
            "SELECT COUNT(*) FROM glaze_cubes "
            "WHERE type = ? AND review_status = 'pending' AND confidence < 0.05 "
            "AND merged_into IS NULL",
            (cube_type,),
        ).fetchone()[0]

        if low_conf_count >= 3:
            rules.append({
                "action": "kill",
                "condition": f"type={cube_type} AND confidence<0.05",
                "cube_type": cube_type,
                "confidence_threshold": 0.05,
                "rule_confidence": 0.8,
                "evidence": f"{low_conf_count} items below 5% confidence (Weibull decay)",
                "rule_type": "decay",
            })

        medium_conf_count = conn.execute(
            "SELECT COUNT(*) FROM glaze_cubes "
            "WHERE type = ? AND review_status = 'pending' AND confidence < 0.10 "
            "AND merged_into IS NULL",
            (cube_type,),
        ).fetchone()[0]

        if medium_conf_count > low_conf_count + 5:
            rules.append({
                "action": "kill",
                "condition": f"type={cube_type} AND confidence<0.10",
                "cube_type": cube_type,
                "confidence_threshold": 0.10,
                "rule_confidence": 0.6,
                "evidence": f"{medium_conf_count} items below 10% confidence (Weibull decay)",
                "rule_type": "decay",
            })

    return rules


def run_auto_triage(conn: sqlite3.Connection, dry_run: bool = False) -> dict:
    """Execute auto-triage on pending cubes. Returns what was triaged and why."""
    rules = compute_triage_rules(conn)
    if not rules:
        return {"triaged": 0, "rules_applied": 0, "actions": [], "rules": []}

    now = datetime.utcnow()
    actions = []

    for rule in rules:
        if rule["rule_confidence"] < 0.5:
            continue

        if rule["action"] == "kill":
            if rule["cube_type"]:
                rows = conn.execute(
                    "SELECT id, title, type, confidence, source, created_at FROM glaze_cubes "
                    "WHERE type = ? AND confidence < ? AND review_status = 'pending' AND merged_into IS NULL",
                    (rule["cube_type"], rule["confidence_threshold"]),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, title, type, confidence, source, created_at FROM glaze_cubes "
                    "WHERE confidence < ? AND review_status = 'pending' AND merged_into IS NULL",
                    (rule["confidence_threshold"],),
                ).fetchall()

        elif rule["action"] == "approve":
            if rule["cube_type"]:
                rows = conn.execute(
                    "SELECT id, title, type, confidence, source, created_at FROM glaze_cubes "
                    "WHERE type = ? AND confidence > ? AND review_status = 'pending' AND merged_into IS NULL",
                    (rule["cube_type"], rule["confidence_threshold"]),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, title, type, confidence, source, created_at FROM glaze_cubes "
                    "WHERE confidence > ? AND review_status = 'pending' AND merged_into IS NULL",
                    (rule["confidence_threshold"],),
                ).fetchall()
        else:
            continue

        seen_ids = {a["cube_id"] for a in actions}
        for row in rows:
            if row["id"] in seen_ids:
                continue
            actions.append({
                "cube_id": row["id"],
                "title": row["title"],
                "type": row["type"],
                "confidence": row["confidence"],
                "source": row["source"],
                "action": rule["action"],
                "reason": rule["evidence"],
                "rule_confidence": rule["rule_confidence"],
            })
            seen_ids.add(row["id"])

    if not dry_run:
        for a in actions:
            conn.execute(
                "UPDATE glaze_cubes SET review_status = ?, review_count = review_count + 1, "
                "last_reinforced = ? WHERE id = ?",
                (a["action"] + "d" if a["action"] == "approve" else "killed", now.isoformat(), a["cube_id"]),
            )
            conn.execute(
                "INSERT INTO reviews (cube_id, decision, notes, time_to_review_seconds, "
                "cube_age_days, cube_type, cube_source, reviewed_at, session_id) "
                "VALUES (?, ?, ?, 0, 0, ?, ?, ?, 'auto-triage')",
                (a["cube_id"], a["action"] + "d" if a["action"] == "approve" else "killed",
                 f"[auto-triage] {a['reason']}", a["type"], a["source"], now.isoformat()),
            )
            _log_triage(conn, a, now)
        conn.commit()

    return {
        "triaged": len(actions),
        "rules_applied": len(rules),
        "dry_run": dry_run,
        "actions": actions[:50],
        "rules": rules,
    }


def _log_triage(conn: sqlite3.Connection, action: dict, now: datetime):
    conn.execute(
        """INSERT INTO triage_log (cube_id, action, reason, rule_confidence, triaged_at)
        VALUES (?, ?, ?, ?, ?)""",
        (action["cube_id"], action["action"], action["reason"],
         action["rule_confidence"], now.isoformat()),
    )


def get_triage_stats(conn: sqlite3.Connection) -> dict:
    """Stats on auto-triage activity."""
    try:
        total = conn.execute("SELECT COUNT(*) FROM triage_log").fetchone()[0]
        by_action = conn.execute(
            "SELECT action, COUNT(*) as cnt FROM triage_log GROUP BY action"
        ).fetchall()
        recent = conn.execute(
            "SELECT cube_id, action, reason, rule_confidence, triaged_at "
            "FROM triage_log ORDER BY triaged_at DESC LIMIT 20"
        ).fetchall()
        avg_confidence = conn.execute(
            "SELECT AVG(rule_confidence) FROM triage_log"
        ).fetchone()[0] or 0

        return {
            "total_triaged": total,
            "by_action": {r["action"]: r["cnt"] for r in by_action},
            "avg_rule_confidence": round(avg_confidence, 3),
            "recent": [dict(r) for r in recent],
        }
    except Exception:
        return {"total_triaged": 0, "by_action": {}, "avg_rule_confidence": 0, "recent": []}


def get_triage_rules(conn: sqlite3.Connection) -> list[dict]:
    return compute_triage_rules(conn)


def init_triage_table(conn: sqlite3.Connection):
    conn.execute("""CREATE TABLE IF NOT EXISTS triage_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cube_id TEXT NOT NULL,
        action TEXT NOT NULL,
        reason TEXT NOT NULL,
        rule_confidence REAL DEFAULT 0,
        triaged_at TEXT NOT NULL
    )""")
    conn.commit()
