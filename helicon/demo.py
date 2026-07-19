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

# A coherent, HIGH-STAKES vault: one founder shipping a live payments product,
# "Ledger". The memories are what their agents actually know — and the rot is
# dangerous, not trivial. A judge feels the stakes: believe the wrong memory and
# an agent charges real customers, writes to the wrong system, or leaks runway.
# (id, source, source_ref, type, title, content, created_at, metadata)
CUBES = [
    # --- HERO contradiction: is Stripe in TEST mode, or LIVE with real money? --
    # An agent that believes "test mode, safe to run a checkout" charges real cards.
    ("demo-stripe-test", "claude-code", "session/2026-03-04", "decision",
     "Stripe mode",
     "Stripe runs in TEST mode — charges are simulated, so it's safe to run the "
     "full checkout end to end while building features.",
     "2026-03-04T10:00:00", {}),
    ("demo-stripe-live", "obsidian", "01 Projects/Ledger/go-live.md", "decision",
     "Stripe is live",
     "We went LIVE on Stripe on 2026-07-01. Every charge is real money now — "
     "never run a live checkout as a test.",
     "2026-07-01T09:00:00", {"as_of": "2026-07-01"}),

    # --- identity fork: what IS 'Ledger'? (an agent writes to the wrong thing) --
    ("demo-ledger-db", "obsidian", "01 Projects/Ledger/architecture.md", "project",
     "Ledger — the database",
     "Ledger is a Postgres database — the production system of record where every "
     "settled transaction is written directly.",
     "2026-05-01T09:00:00", {}),
    ("demo-ledger-svc", "claude-code", "session/2026-06-10", "memory",
     "Ledger notes",
     "Reminder: Ledger is a microservice — it reconciles Stripe payouts nightly "
     "and stores nothing itself.",
     "2026-06-10T09:00:00", {}),

    # --- dead name still asserted (an agent calls a decommissioned service) ----
    ("demo-deadname", "claude-code", "session/2026-02-20", "memory",
     "Charge endpoint",
     "To take a payment, POST to the PayCore service at api.paycore.internal/charge.",
     "2026-02-20T09:00:00", {}),

    # --- freshness: a launch date that has passed -----------------------------
    ("demo-launch", "obsidian", "01 Projects/Ledger/roadmap.md", "decision",
     "Public launch date",
     "Public launch is set for 2026-06-15; freeze new features the week before.",
     "2026-05-01T08:00:00", {"as_of": "2026-05-01", "stale_when": "2026-06-15"}),

    # --- phantom: a speculative claim nothing grounds (auto-managed) -----------
    ("demo-phantom", "obsidian", "03 Ideas/eu-thesis.md", "idea",
     "EU thesis",
     "Ledger rides SEPA to the whole EU market — once SEPA lands, Ledger owns "
     "European payments.",
     "2026-06-15T09:00:00", {}),

    # --- private: a finance fact that must NEVER enter an agent's context ------
    ("demo-runway", "claude-code", "memory/finance.md", "file_created",
     "Runway",
     "Company bank balance is $180,000; runway is roughly 9 months at current burn.",
     "2026-06-28T12:00:00", {}),

    # --- clean controls (so the store isn't all rot, and gates stay honest) ----
    ("demo-stack", "obsidian", "01 Projects/Ledger/architecture.md", "decision",
     "Stack",
     "Ledger's backend is TypeScript on Node with a Fastify API; infra runs on AWS.",
     "2026-05-01T09:00:00", {"as_of": "2026-05-01"}),
    ("demo-name", "claude-code", "session/2026-01-10", "preference",
     "How the founder is addressed",
     "The founder prefers to be called by their first name in all replies.",
     "2026-01-10T09:00:00", {"as_of": "2026-01-10"}),
    ("demo-tz", "obsidian", "profile.md", "preference",
     "Working timezone",
     "The team works from Central European Time; schedule around CET.",
     "2026-05-01T09:00:00", {"as_of": "2026-05-01"}),
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
        if cid == "demo-deadname":   # a dead service name nothing has retrieved in months
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

    # The universally-legible hero: a live contradiction only a human can resolve.
    # value_a/value_b feed the guard, so ruling it ('eats chicken') makes the guard
    # block any later 'the user is vegetarian' — the whole loop on one thread.
    conn.execute(
        "INSERT INTO audit_log (audit_type, target_type, target_id, finding, severity, details, audited_at) "
        "VALUES ('factual', 'claim', 'demo-stripe-live', ?, 'critical', ?, ?)",
        ("Stripe — test mode, or live with real money? Believe the wrong one and "
         "your agent charges real customers.",
         json.dumps({"topic": "Stripe", "value_a": "test mode",
                     "value_b": "live — real money"}),
         "2026-07-01T09:30:00"))
    conn.commit()

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
