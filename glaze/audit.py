import json
import re
import sqlite3
from datetime import datetime

from glaze.models import AuditResult
from glaze.db import insert_audit
from glaze.qwen import detect_contradictions, audit_pattern, resolve_model, complete_json

def _parse_dt(s: str) -> datetime:
    clean = s.replace("Z", "")
    if "+" in clean:
        clean = clean.split("+")[0]
    return datetime.fromisoformat(clean)


TIME_RELATIVE_PATTERNS = [
    r"\bthis week\b", r"\btoday\b", r"\byesterday\b", r"\btomorrow\b",
    r"\bnext week\b", r"\blast week\b", r"\bthis month\b",
    r"\bby end of\b", r"\bthis weekend\b",
]


def audit_temporal(conn: sqlite3.Connection, stale_days: int = 7) -> list[AuditResult]:
    now = datetime.utcnow()
    results = []

    rows = conn.execute(
        "SELECT id, title, content, created_at, type, source FROM glaze_cubes "
        "WHERE review_status = 'pending' AND merged_into IS NULL"
    ).fetchall()

    for row in rows:
        content = row["content"] or ""
        created_at = row["created_at"] or ""

        try:
            created = _parse_dt(created_at)
            age_days = (now - created).total_seconds() / 86400
        except (ValueError, AttributeError):
            continue

        if age_days < stale_days:
            continue

        has_time_ref = False
        matched_phrases = []
        for pattern in TIME_RELATIVE_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                has_time_ref = True
                matched_phrases.append(pattern.replace(r"\b", "").strip())

        if has_time_ref:
            severity = "critical" if age_days > 30 else "warning"
            results.append(AuditResult(
                audit_type="temporal",
                target_type="cube",
                target_id=row["id"],
                finding=f"'{row['title'][:50]}' is {age_days:.0f} days old but contains time-relative language: {', '.join(matched_phrases)}",
                severity=severity,
                proposed_action="flag",
                details={
                    "age_days": round(age_days, 1),
                    "matched_phrases": matched_phrases,
                    "cube_type": row["type"],
                    "source": row["source"],
                },
                audited_at=now.isoformat(),
            ))

    return results


def audit_factual(conn: sqlite3.Connection, qwen_client=None, audit_context: str = "") -> list[AuditResult]:
    now = datetime.utcnow()
    results = []

    rows = conn.execute(
        "SELECT id, title, content, tags, type FROM glaze_cubes "
        "WHERE type = 'memory' AND review_status = 'pending' AND merged_into IS NULL"
    ).fetchall()

    seen_pairs = set()
    for i, a in enumerate(rows):
        a_tags = set(json.loads(a["tags"]) if a["tags"] else [])
        a_title_words = set(a["title"].lower().split())

        for j, b in enumerate(rows):
            if i >= j:
                continue
            pair_key = tuple(sorted([a["id"], b["id"]]))
            if pair_key in seen_pairs:
                continue

            b_tags = set(json.loads(b["tags"]) if b["tags"] else [])
            b_title_words = set(b["title"].lower().split())

            tag_overlap = len(a_tags & b_tags)
            word_overlap = len(a_title_words & b_title_words)

            if tag_overlap < 2 and word_overlap < 3:
                continue

            seen_pairs.add(pair_key)

            if qwen_client:
                result = detect_contradictions(qwen_client, a["content"][:500], b["content"][:500], audit_context=audit_context)
                if result and result.get("contradicts"):
                    results.append(AuditResult(
                        audit_type="factual",
                        target_type="cube",
                        target_id=a["id"],
                        finding=f"Contradiction: '{a['title'][:40]}' vs '{b['title'][:40]}': {result.get('explanation', '')}",
                        severity=result.get("severity", "warning"),
                        proposed_action="flag",
                        details={
                            "cube_a": a["id"],
                            "cube_b": b["id"],
                            "title_a": a["title"],
                            "title_b": b["title"],
                            "explanation": result.get("explanation", ""),
                        },
                        audited_at=now.isoformat(),
                    ))
            else:
                a_content = (a["content"] or "").lower()
                b_content = (b["content"] or "").lower()
                a_name = a["title"].lower()
                b_name = b["title"].lower()

                if _names_suggest_overlap(a_name, b_name):
                    results.append(AuditResult(
                        audit_type="factual",
                        target_type="cube",
                        target_id=a["id"],
                        finding=f"Potential overlap: '{a['title'][:40]}' and '{b['title'][:40]}' may cover the same topic with different information",
                        severity="warning",
                        proposed_action="flag",
                        details={
                            "cube_a": a["id"],
                            "cube_b": b["id"],
                            "title_a": a["title"],
                            "title_b": b["title"],
                            "tag_overlap": list(a_tags & b_tags),
                        },
                        audited_at=now.isoformat(),
                    ))

    return results


def _names_suggest_overlap(name_a: str, name_b: str) -> bool:
    a_parts = set(name_a.replace("-", " ").replace("_", " ").split())
    b_parts = set(name_b.replace("-", " ").replace("_", " ").split())
    stopwords = {"the", "a", "an", "is", "of", "for", "and", "in", "to", "with", "on", "at"}
    a_meaningful = a_parts - stopwords
    b_meaningful = b_parts - stopwords
    if not a_meaningful or not b_meaningful:
        return False
    overlap = len(a_meaningful & b_meaningful)
    return overlap >= 2 and overlap / min(len(a_meaningful), len(b_meaningful)) > 0.5


def audit_decay(conn: sqlite3.Connection) -> list[AuditResult]:
    now = datetime.utcnow()
    results = []

    rows = conn.execute(
        "SELECT id, title, type, confidence, created_at, source FROM glaze_cubes "
        "WHERE confidence < 0.05 AND review_status = 'pending' AND merged_into IS NULL "
        "ORDER BY confidence ASC LIMIT 30"
    ).fetchall()

    for row in rows:
        try:
            created = _parse_dt(row["created_at"])
            age_days = (now - created).total_seconds() / 86400
        except (ValueError, AttributeError):
            age_days = 0

        results.append(AuditResult(
            audit_type="decay",
            target_type="cube",
            target_id=row["id"],
            finding=f"'{row['title'][:50]}' has decayed to {row['confidence']:.1%} confidence ({age_days:.0f} days old, never reviewed). Kill?",
            severity="warning" if row["confidence"] > 0.01 else "critical",
            proposed_action="prune",
            details={
                "confidence": row["confidence"],
                "age_days": round(age_days, 1),
                "cube_type": row["type"],
                "source": row["source"],
            },
            audited_at=now.isoformat(),
        ))

    return results


def audit_patterns_staleness(conn: sqlite3.Connection, qwen_client=None) -> list[AuditResult]:
    now = datetime.utcnow()
    results = []

    rows = conn.execute(
        "SELECT id, name, description, pattern_type, data_points, confidence, "
        "last_reinforced, created_at FROM patterns WHERE status = 'active'"
    ).fetchall()

    for row in rows:
        last_reinforced = row["last_reinforced"] or row["created_at"]
        try:
            last_dt = _parse_dt(last_reinforced)
            days_stale = (now - last_dt).total_seconds() / 86400
        except (ValueError, AttributeError):
            continue

        if days_stale > 30 and row["data_points"] < 10:
            results.append(AuditResult(
                audit_type="logical",
                target_type="pattern",
                target_id=row["id"],
                finding=f"Pattern '{row['name']}' is {days_stale:.0f} days old with only {row['data_points']} data points. Low confidence.",
                severity="warning",
                proposed_action="prune",
                details={
                    "pattern_name": row["name"],
                    "days_stale": round(days_stale, 1),
                    "data_points": row["data_points"],
                    "confidence": row["confidence"],
                },
                audited_at=now.isoformat(),
            ))

    return results


def _build_audit_context(conn: sqlite3.Connection) -> str:
    """ByteRover pattern: inject relevant context before each audit pass."""
    parts = []

    try:
        patterns = conn.execute(
            "SELECT name, description, confidence FROM patterns WHERE status = 'active' ORDER BY confidence DESC LIMIT 5"
        ).fetchall()
        if patterns:
            parts.append("Known review patterns:")
            for p in patterns:
                parts.append(f"  - {p['name']} ({p['confidence']:.0%}): {p['description'][:80]}")
    except Exception:
        pass

    try:
        recent = conn.execute(
            "SELECT decision, COUNT(*) as cnt FROM reviews GROUP BY decision ORDER BY cnt DESC"
        ).fetchall()
        if recent:
            parts.append("Review history: " + ", ".join(f"{r['decision']}={r['cnt']}" for r in recent))
    except Exception:
        pass

    try:
        drift = conn.execute(
            "SELECT kill_rate, total_reviews FROM session_summaries ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if drift:
            parts.append(f"Latest session: {drift['total_reviews']} reviews, {drift['kill_rate']:.0%} kill rate")
    except Exception:
        pass

    try:
        past_findings = conn.execute(
            "SELECT audit_type, COUNT(*) as cnt FROM audit_log WHERE human_decision IS NOT NULL GROUP BY audit_type"
        ).fetchall()
        if past_findings:
            parts.append("Past audit resolutions: " + ", ".join(f"{r['audit_type']}={r['cnt']}" for r in past_findings))
    except Exception:
        pass

    return "\n".join(parts) if parts else ""


def run_audit(conn: sqlite3.Connection, config: dict, qwen_client=None) -> dict:
    audit_config = config.get("audit", {})
    stale_days = audit_config.get("temporal_stale_days", 7)

    audit_context = _build_audit_context(conn)

    all_results = []

    temporal = audit_temporal(conn, stale_days)
    all_results.extend(temporal)

    factual = audit_factual(conn, qwen_client, audit_context)
    all_results.extend(factual)

    decay = audit_decay(conn)
    all_results.extend(decay)

    pattern_stale = audit_patterns_staleness(conn, qwen_client)
    all_results.extend(pattern_stale)

    for result in all_results:
        insert_audit(conn, result)
    conn.commit()

    return {
        "total_findings": len(all_results),
        "by_type": {
            "temporal": len(temporal),
            "factual": len(factual),
            "decay": len(decay),
            "pattern_staleness": len(pattern_stale),
        },
        "by_severity": {
            "critical": sum(1 for r in all_results if r.severity == "critical"),
            "warning": sum(1 for r in all_results if r.severity == "warning"),
            "info": sum(1 for r in all_results if r.severity == "info"),
        },
        "findings": [
            {
                "audit_type": r.audit_type,
                "finding": r.finding,
                "severity": r.severity,
                "proposed_action": r.proposed_action,
                "target_id": r.target_id,
            }
            for r in all_results
        ],
    }
