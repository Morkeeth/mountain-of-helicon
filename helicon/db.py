import json
import os
import sqlite3
from datetime import datetime

from helicon.models import HeliconCube, Review, AuditResult, Pattern

SCHEMA = """
CREATE TABLE IF NOT EXISTS helicon_cubes (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    summary TEXT DEFAULT '',
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    last_reinforced TEXT DEFAULT '',
    confidence REAL DEFAULT 1.0,
    review_status TEXT DEFAULT 'pending',
    review_count INTEGER DEFAULT 0,
    spin_count INTEGER DEFAULT 0,
    novelty_score REAL,
    novelty_action TEXT,
    tags TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}',
    merged_into TEXT,
    UNIQUE(content_hash)
);

CREATE INDEX IF NOT EXISTS idx_cubes_status ON helicon_cubes(review_status);
CREATE INDEX IF NOT EXISTS idx_cubes_source ON helicon_cubes(source);
CREATE INDEX IF NOT EXISTS idx_cubes_type ON helicon_cubes(type);
CREATE INDEX IF NOT EXISTS idx_cubes_confidence ON helicon_cubes(confidence);
CREATE INDEX IF NOT EXISTS idx_cubes_created ON helicon_cubes(created_at);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cube_id TEXT NOT NULL REFERENCES helicon_cubes(id),
    decision TEXT NOT NULL,
    notes TEXT DEFAULT '',
    time_to_review_seconds REAL DEFAULT 0,
    cube_age_days REAL DEFAULT 0,
    cube_type TEXT DEFAULT '',
    cube_source TEXT DEFAULT '',
    reviewed_at TEXT NOT NULL,
    session_id TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_reviews_cube ON reviews(cube_id);
CREATE INDEX IF NOT EXISTS idx_reviews_decision ON reviews(decision);

CREATE TABLE IF NOT EXISTS patterns (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    pattern_type TEXT NOT NULL,
    data_points INTEGER DEFAULT 0,
    confidence REAL DEFAULT 0.5,
    last_reinforced TEXT DEFAULT '',
    last_challenged TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    evidence TEXT DEFAULT '[]',
    status TEXT DEFAULT 'active',
    metadata TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    finding TEXT NOT NULL,
    severity TEXT NOT NULL,
    proposed_action TEXT DEFAULT '',
    human_decision TEXT,
    details TEXT DEFAULT '{}',
    audited_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_log(target_id);
CREATE INDEX IF NOT EXISTS idx_audit_pending ON audit_log(human_decision);
-- concurrency backstop: two processes (watch cron at 00:00 + evolve) racing
-- the same selectors must not double-file. Selectors read-then-insert; these
-- make the insert itself the arbiter.
CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_pair_key
    ON audit_log(json_extract(details, '$.pair_key'))
    WHERE json_extract(details, '$.pair_key') IS NOT NULL AND human_decision IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_stack_key
    ON audit_log(json_extract(details, '$.key'))
    WHERE json_extract(details, '$.key') IS NOT NULL AND human_decision IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_alias_key
    ON audit_log(json_extract(details, '$.alias_key'))
    WHERE json_extract(details, '$.alias_key') IS NOT NULL AND human_decision IS NULL;

CREATE TABLE IF NOT EXISTS retrieval_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id TEXT REFERENCES patterns(id),
    cube_id TEXT REFERENCES helicon_cubes(id),
    context TEXT DEFAULT '',
    was_surfaced INTEGER DEFAULT 0,
    was_acted_on INTEGER DEFAULT 0,
    retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    connectors_used TEXT DEFAULT '[]',
    cubes_added INTEGER DEFAULT 0,
    cubes_merged INTEGER DEFAULT 0,
    cubes_skipped INTEGER DEFAULT 0,
    errors TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nl_text TEXT NOT NULL,
    predicate TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT DEFAULT 'proposed',
    model TEXT DEFAULT '',
    prompt_version TEXT DEFAULT '',
    trust REAL DEFAULT 1.0,
    frozen_examples TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    approved_at TEXT
);

CREATE TABLE IF NOT EXISTS regret_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cube_id TEXT NOT NULL,
    kill_review_id INTEGER,
    task TEXT NOT NULL,
    wanted_at TEXT NOT NULL,
    weight REAL NOT NULL,
    source TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_regret_cube ON regret_events(cube_id);

CREATE TABLE IF NOT EXISTS battery_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    total INTEGER NOT NULL,
    healthy INTEGER NOT NULL,
    degraded INTEGER NOT NULL,
    broken INTEGER NOT NULL,
    mean_tokens INTEGER DEFAULT 0,
    source TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    mention_count INTEGER DEFAULT 1,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    metadata TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);

CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    target_kind TEXT NOT NULL,
    relation TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    metadata TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);

CREATE TABLE IF NOT EXISTS entity_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    old_name TEXT NOT NULL,
    new_name TEXT NOT NULL,
    renamed_at TEXT NOT NULL,
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(old_name, new_name)
);

CREATE TABLE IF NOT EXISTS consolidations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    cube_ids TEXT NOT NULL,
    cube_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    topic TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}'
);
"""


FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS cubes_fts USING fts5(
    title, content, summary, tags,
    content='helicon_cubes',
    content_rowid='rowid'
);
"""

TRIGGER_SCHEMA = """
CREATE TRIGGER IF NOT EXISTS cubes_fts_insert AFTER INSERT ON helicon_cubes BEGIN
    INSERT INTO cubes_fts(rowid, title, content, summary, tags)
    VALUES (new.rowid, new.title, new.content, new.summary, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS cubes_fts_delete AFTER DELETE ON helicon_cubes BEGIN
    INSERT INTO cubes_fts(cubes_fts, rowid, title, content, summary, tags)
    VALUES ('delete', old.rowid, old.title, old.content, old.summary, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS cubes_fts_update AFTER UPDATE ON helicon_cubes BEGIN
    INSERT INTO cubes_fts(cubes_fts, rowid, title, content, summary, tags)
    VALUES ('delete', old.rowid, old.title, old.content, old.summary, old.tags);
    INSERT INTO cubes_fts(rowid, title, content, summary, tags)
    VALUES (new.rowid, new.title, new.content, new.summary, new.tags);
END;
"""


def _migrate_glaze_era(conn: sqlite3.Connection) -> bool:
    """One-time table rename for DBs created before the Mount Helicon rename.
    The FTS table is external-content and its content= option is a stored
    string ALTER TABLE won't rewrite, so it is dropped and rebuilt."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='glaze_cubes'"
    ).fetchone()
    if not row:
        return False
    conn.executescript("""
        DROP TRIGGER IF EXISTS cubes_fts_insert;
        DROP TRIGGER IF EXISTS cubes_fts_delete;
        DROP TRIGGER IF EXISTS cubes_fts_update;
        DROP TABLE IF EXISTS cubes_fts;
        ALTER TABLE glaze_cubes RENAME TO helicon_cubes;
    """)
    conn.commit()
    return True


def human_evidence_sql(prefix: str = "") -> str:
    """The human-evidence guard (rot class R9), as one written predicate.

    Sessions whose reviews may teach rules/patterns/score. Quarantined:
    auto-triage and agent-flag (automation), rule:% (applied rules), and
    seed% (scripted bulk decisions — 90 byte-identical rows from Jun 25
    were counting as human judgment until the Jul 5 audit caught it).
    """
    p = prefix
    return (f"{p}session_id NOT IN ('auto-triage', 'agent-flag') "
            f"AND {p}session_id NOT LIKE 'rule:%' "
            f"AND {p}session_id NOT LIKE 'seed%'")


def init_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # WAL + busy_timeout so a CLI scan and the serving API can share the file
    # without "database is locked" errors.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    migrated = _migrate_glaze_era(conn)
    conn.executescript(SCHEMA)
    conn.commit()
    try:
        conn.executescript(FTS_SCHEMA)
        conn.executescript(TRIGGER_SCHEMA)
        conn.commit()
        if migrated:
            rebuild_fts(conn)
    except sqlite3.OperationalError:
        pass
    return conn


def rebuild_fts(conn: sqlite3.Connection):
    conn.execute("INSERT INTO cubes_fts(cubes_fts) VALUES('rebuild')")
    conn.commit()


def search_cubes(conn: sqlite3.Connection, query: str, limit: int = 30) -> list[dict]:
    rows = conn.execute(
        """SELECT g.*, cubes_fts.rank
        FROM cubes_fts
        JOIN helicon_cubes g ON g.rowid = cubes_fts.rowid
        WHERE cubes_fts MATCH ?
        ORDER BY rank
        LIMIT ?""",
        (query, limit),
    ).fetchall()
    results = []
    for row in rows:
        cube = dict(row)
        cube["tags"] = json.loads(cube["tags"]) if cube["tags"] else []
        cube["metadata"] = json.loads(cube["metadata"]) if cube["metadata"] else {}
        results.append(cube)
    return results


def insert_cube(conn: sqlite3.Connection, cube: HeliconCube) -> bool:
    try:
        conn.execute(
            """INSERT INTO helicon_cubes
            (id, source, source_ref, type, title, content, summary, content_hash,
             created_at, valid_from, last_reinforced, confidence, review_status,
             review_count, spin_count, novelty_score, novelty_action, tags, metadata, merged_into)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cube.id, cube.source, cube.source_ref, cube.type, cube.title,
                cube.content, cube.summary, cube.content_hash, cube.created_at,
                cube.valid_from, cube.last_reinforced, cube.confidence,
                cube.review_status, cube.review_count, cube.spin_count,
                cube.novelty_score, cube.novelty_action,
                json.dumps(cube.tags), json.dumps(cube.metadata), cube.merged_into,
            ),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def insert_review(conn: sqlite3.Connection, review: Review) -> int:
    cursor = conn.execute(
        """INSERT INTO reviews
        (cube_id, decision, notes, time_to_review_seconds, cube_age_days,
         cube_type, cube_source, reviewed_at, session_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            review.cube_id, review.decision, review.notes,
            review.time_to_review_seconds, review.cube_age_days,
            review.cube_type, review.cube_source, review.reviewed_at,
            review.session_id,
        ),
    )
    conn.execute(
        """UPDATE helicon_cubes SET review_status = ?, review_count = review_count + 1,
           last_reinforced = ? WHERE id = ?""",
        (review.decision, review.reviewed_at, review.cube_id),
    )
    return cursor.lastrowid


def log_scan_start(conn: sqlite3.Connection, connectors: list[str]) -> int:
    cursor = conn.execute(
        "INSERT INTO scan_log (started_at, connectors_used) VALUES (?, ?)",
        (datetime.utcnow().isoformat(), json.dumps(connectors)),
    )
    conn.commit()
    return cursor.lastrowid


def log_scan_complete(conn: sqlite3.Connection, scan_id: int, added: int = 0,
                      skipped: int = 0, merged: int = 0, errors: list | None = None):
    conn.execute(
        """UPDATE scan_log SET completed_at = ?, cubes_added = ?, cubes_skipped = ?,
           cubes_merged = ?, errors = ? WHERE id = ?""",
        (datetime.utcnow().isoformat(), added, skipped, merged,
         json.dumps(errors or []), scan_id),
    )
    conn.commit()


def record_battery_point(conn: sqlite3.Connection, total: int, healthy: int,
                         degraded: int, broken: int, mean_tokens: int = 0,
                         source: str = "") -> None:
    """One row per full battery run — the time axis of the degradation curve.
    Every dashboard load and report run adds a real point; nothing is
    interpolated or backfilled."""
    conn.execute(
        """INSERT INTO battery_history
           (recorded_at, total, healthy, degraded, broken, mean_tokens, source)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (datetime.utcnow().isoformat(), total, healthy, degraded, broken,
         mean_tokens, source),
    )
    conn.commit()


def last_scan_info(conn: sqlite3.Connection) -> dict | None:
    """Most recent completed scan, with its age in hours. None if never logged.
    A started-but-never-completed scan doesn't count — only finished ingests
    say anything about memory freshness."""
    row = conn.execute(
        """SELECT completed_at, connectors_used, cubes_added FROM scan_log
           WHERE completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT 1"""
    ).fetchone()
    if not row:
        return None
    completed = datetime.fromisoformat(row["completed_at"])
    hours = (datetime.utcnow() - completed).total_seconds() / 3600
    return {
        "completed_at": row["completed_at"],
        "hours_ago": round(hours, 1),
        "connectors": json.loads(row["connectors_used"] or "[]"),
        "cubes_added": row["cubes_added"],
    }


def insert_audit(conn: sqlite3.Connection, result: AuditResult) -> int | None:
    """Returns the new row id, or None if the unique-key backstop rejected a
    concurrent duplicate (watch cron and evolve racing the same selector)."""
    try:
        cursor = conn.execute(
        """INSERT INTO audit_log
        (audit_type, target_type, target_id, finding, severity,
         proposed_action, human_decision, details, audited_at, resolved_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            result.audit_type, result.target_type, result.target_id,
            result.finding, result.severity, result.proposed_action,
            result.human_decision, json.dumps(result.details),
            result.audited_at, result.resolved_at,
        ),
        )
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None


def get_cubes(
    conn: sqlite3.Connection,
    status: str | None = None,
    source: str | None = None,
    cube_type: str | None = None,
    sort: str = "urgency",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    where = []
    params = []
    if status:
        where.append("review_status = ?")
        params.append(status)
    if source:
        where.append("source = ?")
        params.append(source)
    if cube_type:
        where.append("type = ?")
        params.append(cube_type)

    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    count = conn.execute(f"SELECT COUNT(*) FROM helicon_cubes {where_clause}", params).fetchone()[0]

    order = {
        "urgency": "(1.0 - confidence) DESC, created_at ASC",
        "age": "created_at ASC",
        "confidence": "confidence ASC",
        "newest": "created_at DESC",
    }.get(sort, "(1.0 - confidence) DESC, created_at ASC")

    rows = conn.execute(
        f"SELECT * FROM helicon_cubes {where_clause} ORDER BY {order} LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    cubes = []
    for row in rows:
        cube = dict(row)
        cube["tags"] = json.loads(cube["tags"]) if cube["tags"] else []
        cube["metadata"] = json.loads(cube["metadata"]) if cube["metadata"] else {}
        cubes.append(cube)

    return cubes, count


def get_audit_results(conn: sqlite3.Connection, pending_only: bool = True) -> list[dict]:
    where = "WHERE human_decision IS NULL" if pending_only else ""
    rows = conn.execute(
        f"SELECT * FROM audit_log {where} ORDER BY severity DESC, audited_at DESC"
    ).fetchall()
    results = []
    for row in rows:
        r = dict(row)
        r["details"] = json.loads(r["details"]) if r["details"] else {}
        results.append(r)
    return results


def get_patterns(conn: sqlite3.Connection, active_only: bool = True) -> list[dict]:
    where = "WHERE status = 'active'" if active_only else ""
    rows = conn.execute(
        f"SELECT * FROM patterns {where} ORDER BY confidence DESC"
    ).fetchall()
    results = []
    for row in rows:
        r = dict(row)
        r["evidence"] = json.loads(r["evidence"]) if r["evidence"] else []
        r["metadata"] = json.loads(r["metadata"]) if r["metadata"] else {}
        results.append(r)
    return results
