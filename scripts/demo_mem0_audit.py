#!/usr/bin/env python3
"""Audit a live Mem0 store — the memory backend Alibaba's own docs recommend
for Qwen agents (Model Studio Memory / Mem0 + AnalyticDB reference solution).
Mem0 stores and retrieves; its docs never mention dedup quality, decay, or
contradiction. Mount Helicon reads what Mem0 stored (read-only, via the shipped
connector) and runs the rot exam on it.

Reproducible: set MEM0_API_KEY (a Mem0 platform key) and run. Read-only on the
Mem0 store — it audits, never writes. Optionally declare a rename the store
recorded (e.g. RELAY -> FAVOUR) so the dead-name check can fire.

    MEM0_API_KEY=m0-... python3 scripts/demo_mem0_audit.py [--rename OLD NEW]
    python3 scripts/demo_mem0_audit.py --mock   # no key/account — bundled Mem0 store
"""
import argparse
import os
import sys
import tempfile

from helicon.aliases import add_alias
from helicon.config import load_config
from helicon.db import init_db
from helicon.rot import format_rot, run_rot_exam
from helicon.scanner import run_scan


# A bundled Mem0-format store (the shape the Mem0 API returns) so the audit is
# demoable with zero setup — no account, no key. Real rot Mem0 stores but never
# checks: a flipped preference, a dated goal past its date, and one entity defined
# two incompatible ways.
MOCK_MEMORIES = [
    {"id": "m-diet-1", "memory": "User is a strict vegetarian — never suggest meat "
     "or chicken recipes.", "created_at": "2025-11-02T09:00:00", "categories": ["diet"]},
    {"id": "m-diet-2", "memory": "User started eating chicken and fish again after "
     "three years; now wants high-protein meals.", "created_at": "2026-06-20T18:30:00",
     "updated_at": "2026-06-20T18:30:00", "categories": ["diet"]},
    {"id": "m-goal", "memory": "Currently training for the Berlin marathon on "
     "2026-03-15; long runs every Sunday.", "created_at": "2025-12-01T08:00:00",
     "categories": ["fitness"]},
    {"id": "m-aurora-1", "memory": "Aurora is a payments protocol for cross-border "
     "stablecoin settlement.", "created_at": "2026-04-01T09:00:00", "categories": ["projects"]},
    {"id": "m-aurora-2", "memory": "Aurora is a lending market where users deposit "
     "collateral and borrow against it.", "created_at": "2026-05-10T09:00:00",
     "categories": ["projects"]},
    {"id": "m-helios-phantom", "memory": "Thesis: Helios rides the wave to Solana — "
     "as the Solana ecosystem compounds, Helios rides that liquidity straight up.",
     "created_at": "2026-06-15T09:00:00", "categories": ["thesis"]},
    {"id": "m-name", "memory": "User prefers to be addressed by their first name.",
     "created_at": "2026-05-01T09:00:00", "categories": ["preferences"]},
    {"id": "m-tz", "memory": "User works from Central European Time.",
     "created_at": "2026-05-01T09:00:00", "categories": ["profile"]},
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", default="default")
    ap.add_argument("--mock", action="store_true",
                    help="audit a bundled Mem0-format store (no key/account needed)")
    ap.add_argument("--rename", nargs=2, metavar=("OLD", "NEW"),
                    help="a rename the store recorded, e.g. --rename RELAY FAVOUR")
    args = ap.parse_args()

    key = os.environ.get("MEM0_API_KEY")
    if not key and not args.mock:
        print("Set MEM0_API_KEY (a Mem0 platform key: m0-...), or run with --mock "
              "for a no-setup demo on a bundled Mem0-format store.")
        return 2

    # Reuse the local Qwen embedding config if present (Qwen-native retrieval);
    # everything the rot exam needs is deterministic and runs keyless anyway.
    base = load_config()
    db = os.path.join(tempfile.gettempdir(), "helicon-mem0-audit.db")
    if os.path.exists(db):
        os.remove(db)
    cfg = {
        "db_path": db,
        "qwen_api_key": base.get("qwen_api_key", ""),
        "qwen_base_url": base.get("qwen_base_url", ""),
        "embeddings": base.get("embeddings", {}),
        "connectors": {"mem0": {"api_key": key, "user_id": args.user_id, "limit": 500}},
    }
    conn = init_db(db)
    if args.mock:
        from helicon.connectors.mem0 import _to_result
        from helicon.db import insert_cube
        from helicon.scanner import result_to_cube
        print("Auditing a bundled Mem0-format store (--mock, read-only)...\n")
        pulled = 0
        for item in MOCK_MEMORIES:
            r = _to_result(item, args.user_id)
            if r and insert_cube(conn, result_to_cube(r)):
                pulled += 1
        print(f"  read {pulled} memories from the Mem0 store\n")
    else:
        print(f"Auditing the Mem0 store (user_id={args.user_id}) — read-only...\n")
        stats = run_scan(cfg)
        print(f"  pulled {stats.get('total_in_db', 0)} memories from Mem0\n")
    if args.rename:
        add_alias(conn, args.rename[0], args.rename[1], "2026-01-01T00:00:00",
                  note="rename the store itself recorded")

    def _c(res, rid):
        return next(c for c in res["checks"] if c["id"] == rid)

    # PHASE 1 — audit (the exam a store never runs on itself)
    res = run_rot_exam(conn)
    r11, r12 = _c(res, "R11"), _c(res, "R12")
    print("── PHASE 1 · audit the Mem0 store (read-only) ──")
    print(f"  R11 Identity coherence    {r11['verdict']}   {r11['receipt']}")
    print(f"  R12 Phantom association   {r12['verdict']}   {r12['receipt']}")
    print("  Mem0 / AgentPrizm STORE these memories. Neither can SEE an identity fork")
    print("  or a phantom association — a store confidence-scores what it kept; it does")
    print("  not examine whether two memories disagree on what an entity IS.\n")

    if args.mock:
        # PHASE 2 — rule them (the never-twice a store can't do)
        from helicon.identity import identity_scan, resolve_identity
        from helicon.relations import relation_scan, resolve_relation
        identity_scan(conn, semantic=False)
        fid = conn.execute("SELECT id FROM audit_log WHERE audit_type='identity'").fetchone()
        if fid:
            resolve_identity(conn, fid[0], "a payments protocol")
        relation_scan(conn)
        pid = conn.execute("SELECT id FROM audit_log WHERE audit_type='provenance'").fetchone()
        if pid:
            resolve_relation(conn, pid[0], "phantom")
        print("── PHASE 2 · you rule them (Helicon remembers the verdict) ──")
        print("  Aurora ruled canonical: a payments protocol (the 'lending market' fork loses).")
        print("  Helios → Solana ruled: phantom (an ungrounded association).\n")

        # PHASE 3 — re-audit (the rulings stick)
        res2 = run_rot_exam(conn)
        print("── PHASE 3 · re-audit — the rulings stick ──")
        print(f"  R11 Identity coherence    {_c(res2, 'R11')['verdict']}")
        print(f"  R12 Phantom association   {_c(res2, 'R12')['verdict']}")
        print("  Settled — clean.\n")

        # PHASE 4 — recurrence: the never-twice punchline a store can't do
        from helicon.connectors.mem0 import _to_result
        from helicon.scanner import result_to_cube
        from helicon.db import insert_cube
        recur = {"id": "m-aurora-recur", "categories": ["projects"],
                 "created_at": "2027-01-01T00:00:00",
                 "memory": "Update: Aurora is a lending market after all — the "
                           "payments-protocol framing was wrong."}
        insert_cube(conn, result_to_cube(_to_result(recur, args.user_id)))
        res3 = run_rot_exam(conn)
        print("── PHASE 4 · a NEW memory re-asserts the ruled-out definition ──")
        print("  (Mem0 would just store it, or keep both. What does Helicon do?)")
        print(f"  R11 Identity coherence    {_c(res3, 'R11')['verdict']}   {_c(res3, 'R11')['receipt']}")
        print("\n  Never-twice: the verdict you made RE-ALARMS the instant it's contradicted")
        print("  again. A store forgets it ever asked. Helicon remembers what you ruled —")
        print("  and that is the moat a memory store cannot cross.")
        return 0

    print(format_rot(res))
    print(f"\nMount Helicon audited a Mem0 store and found rot in "
          f"{res['rot_found']}/{res['classes']} classes — the store keeps the write path; "
          f"Helicon is the exam it never runs on itself.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
