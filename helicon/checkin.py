"""Cross-harness context check, over the stores that already exist.

Fleet state owns what is true now.  Transcripto owns the transcript index.
Helicon owns neither: it reads both and grades a harness answer against the
live state.  The score is deliberately small and inspectable, so a later run
can be compared with the same denominator.
"""
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_STATE = "~/.local/state/fleet/CURRENT.md"
DEFAULT_TRACE = "~/.trace/trace.db"
REV_RE = re.compile(r"revision\s+([0-9a-f]{12})")
ANSWER_REV_RE = re.compile(r"(?<![0-9a-f])([0-9a-f]{12})(?![0-9a-f])")
OPEN_RE = re.compile(r"^- \*\*([^*]+)\*\*\s+·\s+(.+)$")
ID_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b")


def _path(value: str) -> Path:
    return Path(os.path.expanduser(value))


def read_state(path: str = DEFAULT_STATE) -> dict:
    """Read the rendered authority without importing or copying its store."""
    p = _path(path)
    text = p.read_text(encoding="utf-8")
    match = REV_RE.search(text)
    if not match:
        raise ValueError(f"no state revision in {p}")

    opened: dict[str, dict] = {}
    closed: set[str] = set()
    section = ""
    current_id = None
    for line in text.splitlines():
        if line.startswith("### CLOSED"):
            section = "closed"
            current_id = None
            continue
        if line == "### OPEN":
            section = "open"
            current_id = None
            continue
        if line.startswith("### "):
            section = ""
            current_id = None
            continue
        item = OPEN_RE.match(line)
        if item and section in ("open", "closed"):
            task_id, rest = item.groups()
            if section == "closed":
                closed.add(task_id)
            else:
                opened[task_id] = {"line": rest, "next": ""}
                current_id = task_id
            continue
        if section == "open" and current_id and line.startswith("  - next: "):
            opened[current_id]["next"] = line.removeprefix("  - next: ").strip()

    return {
        "path": str(p),
        "revision": match.group(1),
        "open": opened,
        "closed": closed,
    }


def transcript_index(path: str = DEFAULT_TRACE, limit: int = 3) -> dict:
    """Read only Transcripto's stable views. Never write or copy messages."""
    p = _path(path)
    if not p.exists():
        return {"path": str(p), "available": False, "harnesses": {},
                "latest_sessions": [], "warnings": None}
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        harnesses = {}
        for r in con.execute(
                "SELECT harness, COUNT(DISTINCT session_id) sessions, "
                "COUNT(*) messages, MAX(ts) latest FROM v_messages GROUP BY harness"
        ):
            latest_ts = r["latest"]
            age_hours = None
            try:
                parsed = datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                age_hours = round((datetime.now(timezone.utc) - parsed).total_seconds() / 3600, 1)
            except (AttributeError, TypeError, ValueError):
                pass
            harnesses[r["harness"] or "unknown"] = {
                "sessions": r["sessions"], "messages": r["messages"],
                "latest": latest_ts, "age_hours": age_hours,
                "freshness": ("unknown" if age_hours is None else
                              "current" if age_hours <= 24 else "stale"),
            }
        latest = [dict(r) for r in con.execute(
            "SELECT session_id, harness, MAX(project) project, MAX(cwd) cwd, "
            "MAX(ts) last_ts, COUNT(*) n_messages FROM v_messages "
            "GROUP BY session_id, harness ORDER BY last_ts DESC LIMIT ?", (limit,)
        )]
        warnings = con.execute(
            "SELECT COUNT(*) FROM v_index_health "
            "WHERE warnings IS NOT NULL AND warnings NOT IN ('', '[]', '{}')"
        ).fetchone()[0]
    finally:
        con.close()
    return {"path": str(p), "available": True, "harnesses": harnesses,
            "latest_sessions": latest, "warnings": warnings}


def memory_candidates(conn: sqlite3.Connection) -> dict:
    """Codex-derived memories stay candidates until a human reviews them."""
    rows = conn.execute(
        "SELECT review_status, COUNT(*) n, MAX(created_at) latest "
        "FROM helicon_cubes WHERE source='codex' GROUP BY review_status"
    ).fetchall()
    by_status = {
        (r["review_status"] or "unlabelled"): {
            "count": r["n"], "latest": r["latest"],
        }
        for r in rows
    }
    return {"source": "codex", "merge_policy": "human-review-only",
            "by_status": by_status,
            "total": sum(v["count"] for v in by_status.values())}


def prompt(snapshot: dict, harness: str) -> str:
    return (
        f"HELICON CHECK-IN · {harness}\n"
        "Without opening a state file now, answer in plain text:\n"
        "1. What is the current 12-character shared-state revision?\n"
        "2. Name exactly five task IDs that are OPEN now.\n"
        "3. Give the current next action for one of those IDs.\n"
        "Do not name closed work. The fixed score is revision 25 + open IDs 50 "
        "+ next action 15 + no closed IDs 10.\n"
        f"Judge source: {snapshot['path']}"
    )


def score_answer(snapshot: dict, answer: str) -> dict:
    revisions = set(ANSWER_REV_RE.findall(answer.lower()))
    ids = set(ID_RE.findall(answer))
    open_ids = ids.intersection(snapshot["open"])
    closed_ids = ids.intersection(snapshot["closed"])

    revision_points = 25 if revisions == {snapshot["revision"]} else 0
    # Exactly five prevents a context dump from gaming a recall check.
    open_points = 10 * len(open_ids) if len(ids) == 5 else 0
    next_matches = []
    lowered = " ".join(answer.lower().split())
    for task_id in open_ids:
        nxt = snapshot["open"][task_id]["next"]
        words = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", nxt) if len(w) >= 5]
        distinctive = words[:6]
        if nxt and distinctive and sum(w in lowered for w in distinctive) >= min(3, len(distinctive)):
            next_matches.append(task_id)
    next_points = 15 if next_matches else 0
    closed_points = 10 if not closed_ids else 0
    score = revision_points + open_points + next_points + closed_points
    return {
        "score": score,
        "out_of": 100,
        "revision": {"points": revision_points, "expected": snapshot["revision"],
                     "found": sorted(revisions)},
        "open_ids": {"points": open_points, "found": sorted(open_ids),
                     "all_ids_in_answer": sorted(ids), "requires_exactly": 5},
        "next_action": {"points": next_points, "matched_ids": sorted(next_matches)},
        "closed_ids": {"points": closed_points, "found": sorted(closed_ids)},
    }
