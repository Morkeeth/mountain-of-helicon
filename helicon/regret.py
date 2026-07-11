"""Regret ledger — LeCaR's ghost-list mechanics on retired memory.

Cache-eviction learning (LeCaR, HotStorage'18): keep a history of what you
evicted; when a request would have hit an evicted item, the eviction is
proven wrong and the regret, discounted by how long ago the eviction was,
feeds back into policy. Here: killed/superseded cubes are the ghost list
(they're tombstoned, never deleted), a retrieval task matching a ghost is a
regret event, and blame lands on the DECISION that killed it (SZZ-style: the
event carries the kill review id), not on the memory.

Regret weight = 0.005 ** (days_since_kill / 30) — a kill wanted again the
same week weighs ~1.0, one wanted after a month weighs 0.005. Constants
visible, like report.py's thresholds.
"""
import re
import sqlite3
from datetime import datetime, timezone

# minimum content words a task must share with a ghost before it counts
MIN_SHARED_TERMS = 3
# same (cube, task) pair only regrets once per day — dashboards reload
DEDUPE_HOURS = 24

_WORD = re.compile(r"[A-Za-z0-9]+")
_STOP = set("the a an and or to of for with when what how this that your you "
            "on in at is are be it as if from into via can will not no do does "
            "before work remaining".split())


def _terms(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "")
            if len(w) > 2 and w.lower() not in _STOP}


def record_ghost_hits(conn: sqlite3.Connection, task: str, source: str = "") -> list[dict]:
    """Match a retrieval task against retired cubes; log a regret event per hit."""
    task_terms = _terms(task)
    if len(task_terms) < 2:
        return []

    query = " OR ".join(sorted(task_terms))
    try:
        ghosts = conn.execute(
            """SELECT g.id, g.title, g.content, g.review_status
               FROM cubes_fts JOIN helicon_cubes g ON g.rowid = cubes_fts.rowid
               WHERE cubes_fts MATCH ? AND g.review_status IN ('killed', 'superseded')
               LIMIT 10""", (query,)
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    hits = []
    for g in ghosts:
        shared = task_terms & _terms(f"{g['title']} {g['content'][:500]}")
        if len(shared) < MIN_SHARED_TERMS:
            continue

        dupe = conn.execute(
            "SELECT 1 FROM regret_events WHERE cube_id = ? AND task = ? "
            "AND wanted_at > datetime(?, ?)",
            (g["id"], task[:200], now.isoformat(), f"-{DEDUPE_HOURS} hours"),
        ).fetchone()
        if dupe:
            continue

        kill = conn.execute(
            "SELECT id, reviewed_at, session_id FROM reviews WHERE cube_id = ? "
            "AND decision = 'killed' ORDER BY reviewed_at DESC LIMIT 1", (g["id"],)
        ).fetchone()
        killed_at = kill["reviewed_at"] if kill else None
        days = 0.0
        if killed_at:
            try:
                days = max(0.0, (now - datetime.fromisoformat(killed_at)).total_seconds() / 86400)
            except ValueError:
                pass
        weight = round(0.005 ** (days / 30), 4) if killed_at else 0.5

        conn.execute(
            "INSERT INTO regret_events (cube_id, kill_review_id, task, wanted_at, weight, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (g["id"], kill["id"] if kill else None, task[:200], now.isoformat(), weight, source),
        )
        hits.append({"cube_id": g["id"], "title": g["title"], "weight": weight,
                     "status": g["review_status"]})
    if hits:
        conn.commit()
    return hits


def get_regrets(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    """Per-cube regret aggregate: how often retrieval wanted something retired."""
    rows = conn.execute(
        """SELECT r.cube_id, COUNT(*) AS events, SUM(r.weight) AS total_weight,
                  MAX(r.wanted_at) AS last_wanted, MIN(r.task) AS sample_task,
                  c.title, c.review_status, c.source AS cube_source,
                  c.source_ref, rv.session_id AS killed_by, rv.reviewed_at AS killed_at
           FROM regret_events r
           JOIN helicon_cubes c ON c.id = r.cube_id
           LEFT JOIN reviews rv ON rv.id = r.kill_review_id
           WHERE c.review_status IN ('killed', 'superseded')
           GROUP BY r.cube_id
           ORDER BY total_weight DESC
           LIMIT ?""", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
