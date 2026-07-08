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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", default="default")
    ap.add_argument("--rename", nargs=2, metavar=("OLD", "NEW"),
                    help="a rename the store recorded, e.g. --rename RELAY FAVOUR")
    args = ap.parse_args()

    key = os.environ.get("MEM0_API_KEY")
    if not key:
        print("Set MEM0_API_KEY (a Mem0 platform key: m0-...) first.")
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
    print(f"Auditing the Mem0 store (user_id={args.user_id}) — read-only...\n")
    stats = run_scan(cfg)
    print(f"  pulled {stats.get('total_in_db', 0)} memories from Mem0\n")
    if args.rename:
        add_alias(conn, args.rename[0], args.rename[1], "2026-01-01T00:00:00",
                  note="rename the store itself recorded")

    res = run_rot_exam(conn)
    print(format_rot(res))
    print(f"\nMount Helicon audited a Mem0 store and found rot in "
          f"{res['rot_found']}/{res['classes']} classes — the store keeps the write path; "
          f"Helicon is the exam it never runs on itself.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
