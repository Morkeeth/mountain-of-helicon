"""The demo store — a first-class package feature so `helicon demo` works from a
fresh clone with no key and no personal data.

NOT real data and NOT the user's store: a separate `helicon-demo.db` of PLANTED
memories that everyone understands at a glance — the classic agent-memory drift
cases. The detectors that fire on them are the REAL ones; only the data is
seeded, and it is labelled `demo` everywhere so it can never be mistaken for a
live audit. Keyless: the deterministic exam is the demo and needs no Qwen key.

Moved here from scripts/demo_seed.py (which now re-exports this) so the demo is
importable from the installed package, not just when the repo is the CWD.
"""
import datetime as _dt
import hashlib
import json
import os

from helicon.db import init_db, insert_cube
from helicon.models import HeliconCube

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DB = os.path.join(_REPO, "data", "helicon-demo.db")
DEMO_CONFIG = os.path.join(_REPO, "config-demo.json")

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
    ("demo-noteapps", "obsidian", "scratch/2025-10-10.md", "decision",
     "Note-taking app comparison",
     "User is comparing Obsidian vs Notion vs Roam for note-taking; leaning "
     "Obsidian for now. Revisit after the trial.",
     "2025-10-10T09:00:00", {"as_of": "2025-10-10"}),

    # --- identity coherence: one entity, two forked definitions --------------
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

    # --- phantom association: a relation no source grounds --------------------
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

    # File the findings a human rules on in the dashboard demo — identity forks
    # + phantom associations — so they appear in the review queue with their
    # resolve controls (deterministic, no embeddings needed).
    from helicon.identity import identity_scan
    from helicon.relations import relation_scan
    identity_scan(conn, semantic=False)
    relation_scan(conn)

    # A couple of already-ruled verdicts so the Golden Rules surface reads as
    # real operating law the moment it is opened (not empty until you rule live).
    from helicon.taste import ingest_verdict
    for i, hsh in enumerate(("taste-le-1", "taste-le-2")):
        ingest_verdict(conn, {
            "artifact_hash": hsh, "kind": "x-reply", "move": "lived-example",
            "human_verdict": "kill", "content": f"draft reply {i}",
            "reason": "shoehorned a fake personal anecdote to seem relatable",
            "decided_at": "2026-07-11T10:00:00", "scores": {"relevance": 0.2}})
    return {"db": db_path, "cubes": n}


def write_demo_config(path: str = DEMO_CONFIG) -> tuple[str, bool]:
    """Write the KEYLESS config the demo store needs, if it is not already there.

    Keyless on purpose: the deterministic exam is the demo, and it needs no key.
    Binds to 127.0.0.1 — the demo never exposes a mutation API to the network.
    Never overwrites an existing file — that one may hold real credentials.
    """
    if os.path.exists(path):
        return path, False
    cfg = {
        "db_path": "data/helicon-demo.db",
        "qwen_api_key": "",
        "qwen_model": "qwen3.6-flash",
        "qwen_base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "connectors": {},
        "server": {"host": "127.0.0.1", "port": 8420, "password": ""},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    return path, True


def ensure_demo() -> dict:
    """Seed a clean demo store and write its keyless config. Idempotent: reseeds
    to a deterministic state every call, so `helicon demo` always opens the same
    compelling dashboard. Returns {db, config, cubes}."""
    res = seed()
    cfg, _ = write_demo_config()
    return {"db": res["db"], "config": cfg, "cubes": res["cubes"]}
