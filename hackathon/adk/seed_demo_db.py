#!/usr/bin/env python3
"""Seed hackathon/adk/demo/helicon.db — sanitized store with UNMEASURABLE wedge.

Counts mirror the *shape* of a real measurement bench run (straddling readings,
wrong-object ratios) without Oscar's personal data. Regenerate freely:

    python3 hackathon/adk/seed_demo_db.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(ROOT))
DEFAULT_DB = os.path.join(ROOT, "demo", "helicon.db")

# Target witness shape (not Oscar's live store — same story, fake IDs)
COUNTS = {
    "total_cubes": 15_001,
    "killed": 9_608,
    "live": 4_739,       # approved, merged_into NULL
    "other": 654,        # pending — sums to total_cubes
    "retrievals": 28,
    "human_rulings": 547,
    "reviews": 9_577,
    "human_reviews": 3,
    "embeddings": 4_214,
}


def _cube_row(i: int, status: str) -> tuple:
    ts = "2026-01-01T00:00:00"
    cid = f"hack-demo-{i:05d}"
    return (
        cid, "hackathon-demo", f"seed/{i}", "memory", f"demo memory {i}",
        "Synthetic demo content — not a real memory.", f"demo-hash-{i:05d}",
        ts, ts, status, None,
    )


def seed(db_path: str = DEFAULT_DB) -> dict:
    if REPO not in sys.path:
        sys.path.insert(0, REPO)

    from helicon.db import init_db
    from helicon.embeddings import init_embedding_table
    from helicon.measure import ensure_schema

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = init_db(db_path)
    init_embedding_table(conn)
    ensure_schema(conn)

    rows: list[tuple] = []
    i = 0
    for _ in range(COUNTS["killed"]):
        rows.append(_cube_row(i, "killed"))
        i += 1
    for _ in range(COUNTS["live"]):
        rows.append(_cube_row(i, "approved"))
        i += 1
    for _ in range(COUNTS["other"]):
        rows.append(_cube_row(i, "pending"))
        i += 1

    conn.executemany(
        "INSERT INTO helicon_cubes (id, source, source_ref, type, title, content, "
        "content_hash, created_at, valid_from, review_status, merged_into) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )

    ts = "2026-08-01T12:00:00"
    conn.executemany(
        "INSERT INTO retrieval_log (retrieved_at) VALUES (?)",
        [(ts,)] * COUNTS["retrievals"],
    )

    conn.executemany(
        "INSERT INTO audit_log (audit_type, target_type, target_id, finding, "
        "severity, human_decision, audited_at) VALUES (?,?,?,?,?,?,?)",
        [
            ("demo", "cube", f"hack-demo-{j:05d}", "demo finding", "low", "kept", ts)
            for j in range(COUNTS["human_rulings"])
        ],
    )

    review_rows = []
    for j in range(COUNTS["reviews"]):
        sid = "cli-human-1" if j < COUNTS["human_reviews"] else "auto-triage"
        review_rows.append(
            (f"hack-demo-{j % COUNTS['live']:05d}", "approved", ts, sid))
    conn.executemany(
        "INSERT INTO reviews (cube_id, decision, reviewed_at, session_id) "
        "VALUES (?,?,?,?)",
        review_rows,
    )

    blob = b"\x00" * 384
    conn.executemany(
        "INSERT INTO cube_embeddings (cube_id, embedding, embedded_at, model, dim) "
        "VALUES (?,?,?,?,?)",
        [
            (f"hack-demo-{j:05d}", blob, ts, "demo-seed", 384)
            for j in range(COUNTS["embeddings"])
        ],
    )

    # Two weeks so measure shows movement on at least one metric (demo video)
    conn.executemany(
        "INSERT INTO weekly_measurements "
        "(recorded_at, week, metric, value, population, unit, command, unmeasured) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [
            ("2026-08-10T12:00:00", "2026-W32", "outward", 1, 16, "artifacts",
             "grep '\"outward\": true' demo-runs/*-lanes.jsonl | wc -l", ""),
            ("2026-08-17T12:00:00", "2026-W33", "outward", 2, 16, "artifacts",
             "grep '\"outward\": true' demo-runs/*-lanes.jsonl | wc -l", ""),
            ("2026-08-10T12:00:00", "2026-W32", "spray_repos", 22, 42, "repos",
             "helicon overboard --code-root <root>", ""),
            ("2026-08-17T12:00:00", "2026-W33", "spray_repos", 21, 42, "repos",
             "helicon overboard --code-root <root>", ""),
        ],
    )

    conn.commit()
    conn.close()

    return {"db_path": db_path, **COUNTS}


def main() -> int:
    out = seed()
    print(f"seeded {out['db_path']}")
    print(f"  cubes={out['total_cubes']} retrievals={out['retrievals']} "
          f"embeddings={out['embeddings']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
