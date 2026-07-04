"""Context snapshots — regression-test what your agent retrieves.

The novel core of Helicon ("CI for agent memory"): capture the approved context
an agent retrieves for a known task (the baseline), then, as memory changes
(new cubes, consolidation, decay, kills), re-run retrieval and DIFF against the
baseline. Surfaces drift the agent would otherwise fail on silently:

  - dropped   : a memory that used to be retrieved no longer is
  - added     : something new pushed into the top-K
  - reordered : the ranking of the shared items changed
  - stale     : a baseline memory is now killed / decayed / removed

This needs no absolute ground truth — only a baseline — so it is not circular
(unlike an LLM judging its own output).
"""
import json
import sqlite3
from datetime import datetime


def init_snapshot_table(conn: sqlite3.Connection):
    conn.execute("""CREATE TABLE IF NOT EXISTS context_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task TEXT NOT NULL,
        cube_ids TEXT NOT NULL,      -- JSON list of ids, ranked order
        titles TEXT NOT NULL,        -- JSON list of titles for readable diffs
        top_k INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        note TEXT DEFAULT ''
    )""")
    conn.commit()


def _drop_superseded(conn: sqlite3.Connection, hits: list[dict], k: int) -> list[dict]:
    """Exclude cubes reconciliation has retired ('superseded') — a re-scan
    replaced them, so serving them is strictly wrong. 'killed'/decayed cubes are
    intentionally left retrievable so the battery can still flag stale context."""
    if not hits:
        return hits
    ids = [h["id"] for h in hits]
    q = ",".join("?" * len(ids))
    gone = {
        r[0] for r in conn.execute(
            f"SELECT id FROM helicon_cubes WHERE id IN ({q}) AND review_status = 'superseded'",
            ids,
        ).fetchall()
    }
    return [h for h in hits if h["id"] not in gone][:k]


def _retrieve(conn: sqlite3.Connection, task: str, k: int) -> list[dict]:
    """Rank memories for a task the way the agent would (hybrid, FTS fallback).
    Over-fetch, then drop superseded, so retiring a stale cube frees its slot."""
    over = k * 3
    try:
        from helicon.embeddings import hybrid_search, get_embedding_stats
        if get_embedding_stats(conn)["embedded"] > 0:
            rows = hybrid_search(conn, task, limit=over)
            if rows:
                hits = [{"id": r["id"], "title": r.get("title", "")} for r in rows]
                return _drop_superseded(conn, hits, k)
    except Exception:
        pass
    # FTS fallback: OR the terms so multi-word queries still match partially
    # (otherwise "consolidation engine" needs BOTH words and can return nothing).
    import re
    from helicon.db import search_cubes
    terms = [t for t in re.findall(r"[A-Za-z0-9]+", task) if len(t) > 2]
    query = " OR ".join(terms) if terms else task
    try:
        rows = search_cubes(conn, query, over)
    except Exception:
        rows = search_cubes(conn, task, over)
    hits = [{"id": r["id"], "title": r["title"]} for r in rows]
    return _drop_superseded(conn, hits, k)


def capture_snapshot(conn: sqlite3.Connection, task: str, k: int = 5, note: str = "") -> dict:
    init_snapshot_table(conn)
    hits = _retrieve(conn, task, k)
    cur = conn.execute(
        "INSERT INTO context_snapshots (task, cube_ids, titles, top_k, created_at, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (task, json.dumps([h["id"] for h in hits]), json.dumps([h["title"] for h in hits]),
         k, datetime.utcnow().isoformat(), note),
    )
    conn.commit()
    return {"id": cur.lastrowid, "task": task, "top_k": k, "hits": hits}


def check_snapshot(conn: sqlite3.Connection, snap: sqlite3.Row) -> dict:
    old_ids = json.loads(snap["cube_ids"])
    old_titles = json.loads(snap["titles"])
    title_of = dict(zip(old_ids, old_titles))
    task, k = snap["task"], snap["top_k"]

    new_hits = _retrieve(conn, task, k)
    new_ids = [h["id"] for h in new_hits]
    new_title_of = {h["id"]: h["title"] for h in new_hits}
    old_set, new_set = set(old_ids), set(new_ids)

    dropped = [title_of[i] for i in old_ids if i not in new_set]
    added = [new_title_of[i] for i in new_ids if i not in old_set]
    common_old = [i for i in old_ids if i in new_set]
    common_new = [i for i in new_ids if i in old_set]
    reordered = common_old != common_new

    stale = []
    for i in old_ids:
        row = conn.execute(
            "SELECT confidence, review_status FROM helicon_cubes WHERE id = ?", (i,)
        ).fetchone()
        if row is None:
            stale.append((title_of[i], "removed"))
        elif row["review_status"] == "killed":
            stale.append((title_of[i], "killed"))
        elif row["review_status"] == "superseded":
            stale.append((title_of[i], "superseded"))
        elif (row["confidence"] or 0) < 0.10:
            stale.append((title_of[i], "decayed"))

    overlap = len(old_set & new_set) / max(1, len(old_set))
    regressed = bool(dropped or added or reordered or stale)
    return {
        "snapshot_id": snap["id"], "task": task,
        "regressed": regressed, "overlap": round(overlap, 2),
        "dropped": dropped, "added": added, "reordered": reordered, "stale": stale,
        "new_titles": [h["title"] for h in new_hits],
    }


def check_all(conn: sqlite3.Connection) -> list[dict]:
    init_snapshot_table(conn)
    rows = conn.execute("SELECT * FROM context_snapshots ORDER BY id").fetchall()
    return [check_snapshot(conn, r) for r in rows]
