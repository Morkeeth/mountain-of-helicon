"""Memory Utility Learning: MemRL-inspired Q-value tracking per cube.

Each memory gets a utility score (Q-value) that updates with every
retrieval+outcome cycle. Memories that get surfaced and acted on rise.
Memories that get surfaced and ignored sink. The Q-value feeds back
into retrieval ranking so the system self-improves over time.

Formula: Q_new = Q_old + alpha * (reward - Q_old)
Retrieval score: (1 - lambda) * relevance + lambda * Q_value

Based on MemRL (github.com/MemTensor/MemRL, arxiv 2601.03192).
"""

import sqlite3
from datetime import datetime


ALPHA = 0.3       # learning rate
LAMBDA = 0.25     # weight of Q-value in retrieval scoring
DEFAULT_Q = 0.5   # uninformed prior


def init_utility_table(conn: sqlite3.Connection):
    conn.execute("""CREATE TABLE IF NOT EXISTS memory_utility (
        cube_id TEXT PRIMARY KEY,
        q_value REAL DEFAULT 0.5,
        times_surfaced INTEGER DEFAULT 0,
        times_acted_on INTEGER DEFAULT 0,
        last_surfaced TEXT,
        last_reward TEXT,
        updated_at TEXT NOT NULL
    )""")
    conn.commit()


def get_q_value(conn: sqlite3.Connection, cube_id: str) -> float:
    row = conn.execute(
        "SELECT q_value FROM memory_utility WHERE cube_id = ?",
        (cube_id,),
    ).fetchone()
    return row["q_value"] if row else DEFAULT_Q


def get_q_values_batch(conn: sqlite3.Connection, cube_ids: list[str]) -> dict:
    if not cube_ids:
        return {}
    placeholders = ",".join("?" * len(cube_ids))
    rows = conn.execute(
        f"SELECT cube_id, q_value FROM memory_utility WHERE cube_id IN ({placeholders})",
        cube_ids,
    ).fetchall()
    result = {r["cube_id"]: r["q_value"] for r in rows}
    for cid in cube_ids:
        if cid not in result:
            result[cid] = DEFAULT_Q
    return result


def record_surfaced(conn: sqlite3.Connection, cube_id: str):
    """Called when a memory is surfaced via glaze_context."""
    init_utility_table(conn)
    now = datetime.utcnow().isoformat()
    existing = conn.execute(
        "SELECT cube_id FROM memory_utility WHERE cube_id = ?", (cube_id,)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE memory_utility SET times_surfaced = times_surfaced + 1, "
            "last_surfaced = ?, updated_at = ? WHERE cube_id = ?",
            (now, now, cube_id),
        )
    else:
        conn.execute(
            "INSERT INTO memory_utility (cube_id, q_value, times_surfaced, "
            "times_acted_on, last_surfaced, updated_at) VALUES (?, ?, 1, 0, ?, ?)",
            (cube_id, DEFAULT_Q, now, now),
        )


def update_reward(conn: sqlite3.Connection, cube_id: str, reward: float):
    """Update Q-value after an outcome (review decision).

    reward: 1.0 = approved/revised (memory was useful)
            0.0 = killed (memory was wrong/stale)
            0.3 = no action (surfaced but not reviewed - slight negative)
    """
    init_utility_table(conn)
    now = datetime.utcnow().isoformat()
    q_old = get_q_value(conn, cube_id)
    q_new = round(q_old + ALPHA * (reward - q_old), 4)

    existing = conn.execute(
        "SELECT cube_id FROM memory_utility WHERE cube_id = ?", (cube_id,)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE memory_utility SET q_value = ?, "
            "times_acted_on = times_acted_on + 1, "
            "last_reward = ?, updated_at = ? WHERE cube_id = ?",
            (q_new, now, now, cube_id),
        )
    else:
        conn.execute(
            "INSERT INTO memory_utility (cube_id, q_value, times_surfaced, "
            "times_acted_on, last_reward, updated_at) VALUES (?, ?, 0, 1, ?, ?)",
            (cube_id, q_new, now, now),
        )


def decay_unsurfaced(conn: sqlite3.Connection, decay_rate: float = 0.02):
    """Slightly decay Q-values of memories not surfaced recently.
    Prevents stale high-Q memories from dominating forever."""
    init_utility_table(conn)
    conn.execute(
        "UPDATE memory_utility SET q_value = MAX(0.1, q_value - ?) "
        "WHERE last_surfaced < datetime('now', '-7 days')",
        (decay_rate,),
    )
    conn.commit()


def get_utility_stats(conn: sqlite3.Connection) -> dict:
    init_utility_table(conn)
    rows = conn.execute(
        "SELECT mu.cube_id, mu.q_value, mu.times_surfaced, mu.times_acted_on, "
        "gc.title, gc.type FROM memory_utility mu "
        "JOIN glaze_cubes gc ON mu.cube_id = gc.id "
        "ORDER BY mu.q_value DESC"
    ).fetchall()

    if not rows:
        return {"total_tracked": 0, "avg_q": DEFAULT_Q, "top": [], "bottom": []}

    q_values = [r["q_value"] for r in rows]
    return {
        "total_tracked": len(rows),
        "avg_q": round(sum(q_values) / len(q_values), 3),
        "top": [
            {"cube_id": r["cube_id"], "title": r["title"][:50], "type": r["type"],
             "q_value": r["q_value"], "surfaced": r["times_surfaced"],
             "acted_on": r["times_acted_on"]}
            for r in rows[:10]
        ],
        "bottom": [
            {"cube_id": r["cube_id"], "title": r["title"][:50], "type": r["type"],
             "q_value": r["q_value"], "surfaced": r["times_surfaced"],
             "acted_on": r["times_acted_on"]}
            for r in rows[-10:]
        ] if len(rows) > 10 else [],
    }
