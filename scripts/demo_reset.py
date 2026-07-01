#!/usr/bin/env python3
"""Reset and re-seed the database for a clean demo recording."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.chdir(os.path.dirname(os.path.dirname(__file__)))

from glaze.config import load_config
from glaze.db import init_db
from glaze.scanner import run_scan
from glaze.forgetting import apply_decay
from glaze.audit import run_audit
from glaze.patterns import extract_patterns_from_sql, save_patterns
from glaze.score import compute_score
from glaze.qwen import get_client

config = load_config()
db_path = config.get("db_path", "data/glaze.db")

if os.path.exists(db_path):
    os.remove(db_path)
    print(f"Removed {db_path}")

print("\n=== Step 1: Scan all connectors ===")
stats = run_scan(config)
print(f"Added: {stats['added']}, Skipped: {stats['skipped']}")
print(f"By source: {stats['by_source']}")
print(f"Total in DB: {stats['total_in_db']}")

conn = init_db(db_path)

print("\n=== Step 2: Apply Ebbinghaus decay ===")
decay = apply_decay(conn, config)
print(f"Updated: {decay['updated']}, Critical: {decay['critical_decay']}")

print("\n=== Step 3: Run audit ===")
client = get_client(config)
audit = run_audit(conn, config, client)
print(f"Findings: {audit['total_findings']}")
print(f"By type: {audit['by_type']}")
print(f"By severity: {audit['by_severity']}")

print("\n=== Step 4: Extract patterns ===")
patterns = extract_patterns_from_sql(conn)
save_patterns(conn, patterns)
print(f"Patterns: {len(patterns)}")

print("\n=== Step 5: Glaze Score ===")
score = compute_score(conn)
print(f"Score: {score['score']}% ({score['reviewed']}/{score['total']})")

conn.close()
print("\n=== Demo DB ready ===")
