"""Battery report — run the context-quality battery over the real benchmark
task set and print an honest verdict distribution.

Uses eval._build_test_queries (queries derived from real approved cubes), so
the numbers are on live memory, not a fixture. Answers: for how many real
retrieval tasks is the agent's memory HEALTHY vs DEGRADED vs BROKEN, and why?

Run:  python3 scripts/battery_report.py
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from glaze.config import load_config
from glaze.db import init_db
from glaze.eval import _build_test_queries
from glaze.battery import run_battery

K = 5


def main():
    config = load_config()
    conn = init_db(config["db_path"])
    queries = _build_test_queries(conn)
    if not queries:
        print("No benchmark queries (empty/unlabelled db).")
        return

    verdicts = Counter()
    test_fails = Counter()
    rows = []
    for q in queries:
        res = run_battery(conn, q["query"], k=K)
        verdicts[res["verdict"]] += 1
        for r in res["results"]:
            if r["status"] == "FAIL":
                test_fails[r["name"]] += 1
        rows.append((res["verdict"], q["query"], res["results"]))

    n = len(queries)
    print(f"\n{'='*70}\nBATTERY REPORT — {n} real benchmark tasks, top-{K}, db={config['db_path']}\n{'='*70}")
    for v in ("HEALTHY", "DEGRADED", "BROKEN"):
        c = verdicts[v]
        bar = "#" * c
        print(f"  {v:9} {c:3}/{n}  {int(100*c/n):3}%  {bar}")

    print(f"\n  Failing tests (across all tasks):")
    for name, c in test_fails.most_common():
        print(f"    {name:13} failed on {c}/{n} tasks")

    print(f"\n  Worst tasks (BROKEN, with reasons):")
    shown = 0
    for verdict, query, results in rows:
        if verdict == "BROKEN" and shown < 6:
            fails = [f"{r['name']}({r['reason']})" for r in results if r["status"] == "FAIL"]
            print(f"    - \"{query}\": {'; '.join(fails)}")
            shown += 1

    print(f"\n  Honest read: {verdicts['BROKEN']}/{n} tasks retrieve killed/decayed context "
          f"(BROKEN); {verdicts['DEGRADED']}/{n} have a non-critical quality issue.")
    print("  These are real memories to clean, not a synthetic score.\n")


if __name__ == "__main__":
    main()
