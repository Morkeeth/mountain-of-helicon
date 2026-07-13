"""Seed a small, universally-legible demo store for the self-healing audit loop.

NOT real data and NOT the user's store: a separate `helicon-demo.db` with a
handful of PLANTED memories that everyone understands at a glance — the classic
agent-memory drift cases. The detectors that fire on them are the REAL ones
(claims / volatility / freshness); only the data is seeded, and it is labelled
demo everywhere so it can never be mistaken for the live audit.

Three planted drifts, one per gate that the repair loop can move:

  consistency  "User is vegetarian" (Nov 2025) vs "started eating chicken
               again" (Jun 2026). The textbook stale-preference contradiction.
  freshness    "Training for the Berlin marathon, 2026-03-15" — the date has
               passed; a goal memory that decayed into a lie.
  volatility   "Checking account balance is $4,200 as of last week" — a fast
               fact stored as durable memory; it belongs in the live layer.

Run:  python3 scripts/demo_seed.py         # (re)build data/helicon-demo.db
Idempotent: it drops and rebuilds the cubes each run, so it doubles as reset.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helicon.db import init_db, insert_cube
from helicon.models import HeliconCube

DEMO_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "helicon-demo.db")

# (id, source, source_ref, type, title, content, created_at, metadata)
# Qualifiers are planted so the REAL deterministic selectors bind them: the two
# diet memories share "dietary/preference"; the marathon carries stale_when; the
# balance line carries a $ + "last week" fast-fact signal.
CUBES = [
    # --- consistency: the stale-preference contradiction (the hero) ----------
    ("demo-diet-old", "claude-code", "session/2025-11-02", "preference",
     "Dietary preference",
     "User's dietary preference: strict vegetarian. Never suggest meat or "
     "chicken recipes; keep every meal plan plant-based.",
     "2025-11-02T09:00:00", {}),
    ("demo-diet-new", "chatgpt", "chat/2026-06-20", "preference",
     "Dietary preference update",
     "User's dietary preference changed: started eating chicken and fish "
     "again after three years. Wants high-protein meals now.",
     "2026-06-20T18:30:00", {"as_of": "2026-06-20"}),

    # --- freshness: a dated goal whose date has passed ------------------------
    ("demo-marathon", "obsidian", "goals.md", "decision",
     "Current training goal",
     "Currently training for the Berlin marathon on 2026-03-15. Long runs "
     "every Sunday, tapering the last two weeks.",
     "2025-12-01T08:00:00", {"as_of": "2025-12-01", "stale_when": "2026-03-15"}),

    # --- volatility: a fast fact stored as durable memory ---------------------
    ("demo-balance", "claude-code", "memory/finance.md", "file_created",
     "Account balance",
     "User's checking account balance is $4,200 as of last week; they are "
     "saving toward a deposit.",
     "2026-06-28T12:00:00", {}),

    # --- retrieval: a dead memory nothing has retrieved in months -----------
    # A resolved, transient note — long settled, never surfaced since. Dead
    # weight that dilutes retrieval. The usage log (seeded below) gives every
    # other memory recent hits and this one none, so it stands out as a kill
    # candidate exactly as the truth-gate spec defines the retrieval gate.
    ("demo-noteapps", "obsidian", "scratch/2025-10-10.md", "decision",
     "Note-taking app comparison",
     "User is comparing Obsidian vs Notion vs Roam for note-taking; leaning "
     "Obsidian for now. Revisit after the trial.",
     "2025-10-10T09:00:00", {"as_of": "2025-10-10"}),

    # --- R11 identity coherence: one entity, two forked definitions ----------
    # Two grounded sources define "Aurora" with incompatible genera (protocol vs
    # market). Article-gated, cross-source -> the identity gate fires.
    ("demo-aurora-a", "obsidian", "01 Projects/Aurora/overview.md", "project",
     "Aurora — overview",
     "Aurora is a payments protocol for cross-border stablecoin settlement; it "
     "routes transfers between chains.",
     "2026-04-01T09:00:00", {}),
    ("demo-aurora-b", "claude-code", "session/2026-05-10", "memory",
     "Aurora notes",
     "Reminder: Aurora is a lending market — users deposit collateral and borrow "
     "against it at a variable rate.",
     "2026-05-10T09:00:00", {}),

    # --- R12 phantom association: a relation no source grounds ----------------
    # A single idea note claims a relation between two entities that nothing else
    # corroborates -> the phantom-association gate fires.
    ("demo-aurora-phantom", "obsidian", "03 Ideas/aurora-thesis.md", "idea",
     "Aurora thesis",
     "Aurora rides the wave to Solana — if the Solana ecosystem keeps growing, "
     "Aurora rides that momentum straight up.",
     "2026-06-15T09:00:00", {}),

    # --- clean control memories (so scores are not 0/100 and gates are honest) -
    ("demo-name", "claude-code", "session/2025-10-01", "preference",
     "How the user is addressed",
     "User prefers to be called by their first name in all replies.",
     "2025-10-01T09:00:00", {"as_of": "2025-10-01"}),
    ("demo-tz", "obsidian", "profile.md", "preference",
     "Working timezone",
     "User works from the Central European Time zone; schedule around CET.",
     "2026-05-01T09:00:00", {"as_of": "2026-05-01"}),
    ("demo-style", "chatgpt", "chat/2026-05-15", "preference",
     "Code style",
     "User prefers concise code with no unnecessary comments.",
     "2026-05-15T11:00:00", {"as_of": "2026-05-15"}),
]


def seed(db_path: str = DEMO_DB) -> dict:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = init_db(db_path)
    # Idempotent reset: clear cubes + any findings from a prior run.
    conn.execute("DELETE FROM helicon_cubes")
    conn.execute("DELETE FROM audit_log")
    conn.commit()

    n = 0
    for cid, source, ref, ctype, title, content, created, meta in CUBES:
        cube = HeliconCube(
            id=cid, source=source, source_ref=ref, type=ctype, title=title,
            content=content, summary=content[:120],
            content_hash=hashlib.sha1(content.encode()).hexdigest(),
            created_at=created, valid_from=created, last_reinforced=created,
            confidence=1.0, review_status="pending", tags=["demo"], metadata=meta,
        )
        if insert_cube(conn, cube):
            n += 1

    # Seed a usage log: every memory has been surfaced recently EXCEPT the dead
    # note-app comparison — so the retrieval gate flags exactly one kill
    # candidate, and retiring it moves the gate.
    import datetime as _dt
    recent = (_dt.datetime.utcnow() - _dt.timedelta(days=3)).isoformat()
    conn.execute("DELETE FROM retrieval_log")
    for cid, *_ in CUBES:
        if cid == "demo-noteapps":
            continue
        for _ in range(2):
            conn.execute(
                "INSERT INTO retrieval_log (cube_id, context, was_surfaced, "
                "was_acted_on, retrieved_at) VALUES (?, 'demo', 1, 0, ?)",
                (cid, recent))
    conn.commit()
    return {"db": db_path, "cubes": n}


if __name__ == "__main__":
    result = seed()
    print(f"seeded {result['cubes']} demo cubes -> {result['db']}")
