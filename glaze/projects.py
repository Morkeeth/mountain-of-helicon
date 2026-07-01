"""Project Intelligence layer.

Groups cubes by project tag, computes rollup metrics (ship rate, spin score,
decay velocity), detects context-switch cost, and generates ranked
recommendations for what to work on next.
"""

import json
import sqlite3
from datetime import datetime, timedelta


# Optional: merge tag variants into one canonical project name. Empty by default
# and data-driven - any meaningful tag is treated as a project, so this works for
# any user's repos without shipping a hardcoded personal project list.
PROJECT_ALIASES: dict[str, str] = {}

# Generic tags that are not projects, so they don't get grouped as one.
_NON_PROJECT_TAGS = {
    "code", "memory", "note", "notes", "misc", "general", "todo", "draft",
    "idea", "review", "task", "update", "wip", "doc", "docs", "test",
}


def _normalize_project(tag: str) -> str | None:
    tag = tag.strip().lower()
    if len(tag) < 2 or tag in _NON_PROJECT_TAGS:
        return None
    return PROJECT_ALIASES.get(tag, tag)


def _extract_projects(tags_json: str) -> set[str]:
    try:
        tags = json.loads(tags_json) if tags_json else []
    except (json.JSONDecodeError, TypeError):
        return set()
    projects = set()
    for t in tags:
        p = _normalize_project(t)
        if p:
            projects.add(p)
    return projects


def get_project_rollup(conn) -> list[dict]:
    """Compute per-project stats from cubes + reviews."""
    now = datetime.utcnow()

    rows = conn.execute("""
        SELECT c.id, c.tags, c.source, c.source_ref, c.type, c.confidence,
               c.review_status, c.created_at, c.spin_count
        FROM glaze_cubes c
        WHERE c.merged_into IS NULL
    """).fetchall()

    reviews = {}
    for r in conn.execute("SELECT cube_id, decision FROM reviews").fetchall():
        reviews[r["cube_id"]] = r["decision"]

    projects: dict[str, dict] = {}

    for row in rows:
        cube_projects = _extract_projects(row["tags"])
        if not cube_projects:
            continue

        for proj in cube_projects:
            if proj not in projects:
                projects[proj] = {
                    "name": proj,
                    "cube_count": 0,
                    "sessions": set(),
                    "sources": set(),
                    "approved": 0,
                    "killed": 0,
                    "revised": 0,
                    "pending": 0,
                    "total_confidence": 0.0,
                    "total_spin": 0,
                    "latest_output": None,
                    "types": {},
                }

            p = projects[proj]
            p["cube_count"] += 1
            p["sources"].add(row["source"])
            if row["source_ref"] and row["source_ref"].startswith("session_"):
                p["sessions"].add(row["source_ref"])

            status = row["review_status"]
            decision = reviews.get(row["id"])
            if decision == "approved":
                p["approved"] += 1
            elif decision == "killed":
                p["killed"] += 1
            elif decision == "revised":
                p["revised"] += 1
            elif status == "pending":
                p["pending"] += 1

            p["total_confidence"] += row["confidence"]
            p["total_spin"] += row["spin_count"] or 0

            t = row["type"]
            p["types"][t] = p["types"].get(t, 0) + 1

            try:
                raw = row["created_at"].replace("Z", "").split("+")[0]
                created = datetime.fromisoformat(raw)
            except (ValueError, AttributeError):
                continue

            is_output = (
                row["source"] == "git"
                or decision == "approved"
                or row["type"] in ("code", "file_created")
            )
            if is_output:
                if p["latest_output"] is None or created > p["latest_output"]:
                    p["latest_output"] = created

    result = []
    for proj, p in projects.items():
        total_reviewed = p["approved"] + p["killed"] + p["revised"]
        ship_rate = p["approved"] / max(total_reviewed, 1)
        session_count = len(p["sessions"])
        shipped = p["approved"]

        spin_score = session_count / max(shipped, 1) if session_count > 0 else 0

        avg_confidence = p["total_confidence"] / max(p["cube_count"], 1)

        days_since_output = None
        if p["latest_output"]:
            days_since_output = (now - p["latest_output"]).days

        decay_velocity = 1.0 - avg_confidence

        result.append({
            "name": proj,
            "cube_count": p["cube_count"],
            "session_count": session_count,
            "ship_rate": round(ship_rate, 3),
            "shipped": shipped,
            "killed": p["killed"],
            "revised": p["revised"],
            "pending": p["pending"],
            "spin_score": round(spin_score, 1),
            "days_since_output": days_since_output,
            "avg_confidence": round(avg_confidence, 3),
            "decay_velocity": round(decay_velocity, 3),
            "sources": sorted(p["sources"]),
            "types": p["types"],
        })

    result.sort(key=lambda x: x["cube_count"], reverse=True)
    return result


def get_recommendations(conn, config: dict | None = None) -> list[dict]:
    """Rank projects by urgency and return one-line recommendation each."""
    projects = get_project_rollup(conn)
    if not projects:
        return []

    scored = []
    for p in projects:
        if p["cube_count"] < 3:
            continue

        score = 0.0
        reasons = []

        if p["spin_score"] > 3.0:
            score += 30
            reasons.append(f"spin score {p['spin_score']}x - lots of talk, little shipped")
        elif p["spin_score"] > 1.5:
            score += 15
            reasons.append(f"spin score {p['spin_score']}x")

        if p["days_since_output"] is not None:
            if p["days_since_output"] > 14:
                score += 25
                reasons.append(f"no output in {p['days_since_output']}d")
            elif p["days_since_output"] > 7:
                score += 10
                reasons.append(f"last output {p['days_since_output']}d ago")

        if p["decay_velocity"] > 0.7:
            score += 20
            reasons.append(f"decaying fast ({p['avg_confidence']:.0%} avg confidence)")

        if p["pending"] > 10:
            score += 15
            reasons.append(f"{p['pending']} items unreviewed")

        if p["ship_rate"] > 0.3 and p["shipped"] >= 2:
            score += 10
            reasons.append(f"shipping momentum ({p['ship_rate']:.0%} rate)")

        if p["ship_rate"] == 0 and p["cube_count"] > 10:
            score += 20
            reasons.append(f"{p['cube_count']} cubes, 0 shipped")

        action = _pick_action(p, reasons)

        scored.append({
            "name": p["name"],
            "score": round(score, 1),
            "action": action,
            "reasons": reasons,
            "cube_count": p["cube_count"],
            "ship_rate": p["ship_rate"],
            "spin_score": p["spin_score"],
            "days_since_output": p["days_since_output"],
            "pending": p["pending"],
            "avg_confidence": p["avg_confidence"],
        })

    scored.sort(key=lambda x: x["score"], reverse=True)

    from glaze.qwen import get_client, complete
    client = get_client(config or {})
    if client:
        _enrich_with_qwen(client, scored, config)

    return scored


def _pick_action(p: dict, reasons: list[str]) -> str:
    if p["ship_rate"] == 0 and p["cube_count"] > 10:
        return f"Ship or kill. {p['cube_count']} cubes, nothing approved."
    if p["spin_score"] > 3.0:
        return f"Stop planning, start shipping. {p['spin_score']:.0f} sessions per shipped item."
    if p["days_since_output"] and p["days_since_output"] > 14:
        return f"Stale {p['days_since_output']}d. Either push a commit or archive."
    if p["decay_velocity"] > 0.7:
        return f"Memory decaying ({p['avg_confidence']:.0%}). Review or it rots."
    if p["pending"] > 10:
        return f"Review backlog: {p['pending']} items waiting."
    if p["ship_rate"] > 0.3 and p["shipped"] >= 2:
        return f"Hot hand. {p['shipped']} shipped at {p['ship_rate']:.0%} rate. Keep going."
    return f"{p['cube_count']} cubes across {len(reasons)} signals."


def _enrich_with_qwen(client, projects: list[dict], config: dict | None = None):
    from glaze.qwen import complete, resolve_model
    model = resolve_model("fast", config)

    summary = "\n".join(
        f"- {p['name']}: {p['cube_count']} cubes, ship rate {p['ship_rate']:.0%}, "
        f"spin {p['spin_score']:.1f}x, last output {p['days_since_output'] or '?'}d ago, "
        f"action: {p['action']}"
        for p in projects[:8]
    )

    try:
        result = complete(
            client,
            "You are a project advisor. Given these project stats, write a one-line recommendation for each (max 15 words). Be direct and specific. Format: project_name: recommendation",
            summary,
            model=model,
            operation="project_recommend",
        )
        if result:
            for line in result.strip().split("\n"):
                if ":" in line:
                    name, rec = line.split(":", 1)
                    name = name.strip().lower().replace(" ", "-")
                    for p in projects:
                        if p["name"] == name or name in p["name"]:
                            p["action"] = rec.strip()
    except Exception:
        pass


def get_weekly_summary(conn) -> dict:
    """Weekly summary: projects touched, projects shipped from."""
    now = datetime.utcnow()
    week_ago = (now - timedelta(days=7)).isoformat()

    touched = set()
    shipped_from = set()

    rows = conn.execute("""
        SELECT c.tags, c.review_status
        FROM glaze_cubes c
        WHERE c.created_at > ? AND c.merged_into IS NULL
    """, (week_ago,)).fetchall()

    for row in rows:
        projs = _extract_projects(row["tags"])
        touched.update(projs)

    review_rows = conn.execute("""
        SELECT c.tags FROM reviews r
        JOIN glaze_cubes c ON r.cube_id = c.id
        WHERE r.reviewed_at > ? AND r.decision = 'approved'
    """, (week_ago,)).fetchall()

    for row in review_rows:
        projs = _extract_projects(row["tags"])
        shipped_from.update(projs)

    return {
        "touched": sorted(touched),
        "touched_count": len(touched),
        "shipped_from": sorted(shipped_from),
        "shipped_count": len(shipped_from),
        "week_start": week_ago[:10],
    }


def get_context_switches(conn: sqlite3.Connection, weeks: int = 4) -> dict:
    """Detect sessions touching 3+ project tags with 0 shipped items.

    Returns a weekly context-switch index and flagged sessions.
    """
    now = datetime.utcnow()
    cutoff = (now - timedelta(weeks=weeks)).isoformat()

    # Get all claude-code sessions since cutoff with their cubes
    rows = conn.execute("""
        SELECT c.source_ref AS session_id,
               c.tags,
               c.review_status,
               c.created_at
        FROM glaze_cubes c
        WHERE c.source = 'claude-code'
          AND c.created_at > ?
          AND c.merged_into IS NULL
    """, (cutoff,)).fetchall()

    # Group by session
    sessions: dict[str, dict] = {}
    for row in rows:
        sid = row["session_id"]
        if not sid:
            continue
        if sid not in sessions:
            sessions[sid] = {
                "project_tags": set(),
                "cube_count": 0,
                "approved": 0,
                "earliest": row["created_at"],
            }
        s = sessions[sid]
        s["cube_count"] += 1
        if row["review_status"] == "approved":
            s["approved"] += 1

        projs = _extract_projects(row["tags"])
        s["project_tags"].update(projs)

        # Track earliest date
        if row["created_at"] and row["created_at"] < s["earliest"]:
            s["earliest"] = row["created_at"]

    # Bucket by ISO week
    week_buckets: dict[str, dict] = {}
    flagged = []

    for sid, s in sessions.items():
        # Determine week
        try:
            dt = datetime.fromisoformat(
                s["earliest"].replace("Z", "").split("+")[0]
            )
            iso_week = dt.strftime("%Y-W%W")
        except (ValueError, AttributeError):
            iso_week = "unknown"

        if iso_week not in week_buckets:
            week_buckets[iso_week] = {
                "week": iso_week,
                "sessions": 0,
                "multi_project_sessions": 0,
                "zero_ship_multi": 0,
                "projects_touched": set(),
            }

        bucket = week_buckets[iso_week]
        bucket["sessions"] += 1
        bucket["projects_touched"].update(s["project_tags"])

        if len(s["project_tags"]) >= 3:
            bucket["multi_project_sessions"] += 1
            if s["approved"] == 0:
                bucket["zero_ship_multi"] += 1
                flagged.append({
                    "session_id": sid,
                    "project_tags": sorted(s["project_tags"]),
                    "cube_count": s["cube_count"],
                    "approved": s["approved"],
                })

    weekly = []
    for week in sorted(week_buckets.keys()):
        bucket = week_buckets[week]
        total_sessions = bucket["sessions"]
        multi = bucket["multi_project_sessions"]
        switch_index = round(multi / max(total_sessions, 1), 3)
        weekly.append({
            "week": week,
            "sessions": total_sessions,
            "multi_project_sessions": multi,
            "zero_ship_multi": bucket["zero_ship_multi"],
            "projects_touched": len(bucket["projects_touched"]),
            "switch_index": switch_index,
        })

    avg_index = (
        round(sum(w["switch_index"] for w in weekly) / max(len(weekly), 1), 3)
        if weekly else 0
    )

    return {
        "weeks_analyzed": len(weekly),
        "avg_switch_index": avg_index,
        "weekly": weekly,
        "flagged_sessions": flagged[:20],
    }
