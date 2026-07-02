"""Demo: regression-test a coding-agent's memory (end-to-end, public data).

Proves the whole Helicon loop on a repo's OWN committed agent rules — no
personal data, reproducible by anyone with this repo:

  1. Ingest the repo's agent-memory (CLAUDE.md sections) as cubes.
  2. Snapshot what the agent retrieves for a known task (the baseline).
  3. Simulate memory drift (a consolidation pass kills/drops a rule).
  4. Re-check the snapshot -> the regression is caught automatically.

Run:  python3 scripts/demo_agent_rules_regression.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from glaze.connectors import agent_rules
from glaze.scanner import result_to_cube
from glaze.db import init_db, insert_cube, rebuild_fts
from glaze.snapshots import capture_snapshot, check_all

REPO = os.path.expanduser(os.environ.get("DEMO_REPO", "~/CODE/glaze"))
TASK = "how do I run the backend dev server"
K = 3


def banner(msg):
    print(f"\n{'='*66}\n{msg}\n{'='*66}")


def main():
    db_path = os.path.join(tempfile.mkdtemp(prefix="helicon-demo-"), "demo.db")
    conn = init_db(db_path)

    # 1. INGEST the repo's agent memory (its own CLAUDE.md, public data).
    banner(f"1. INGEST agent memory from {os.path.basename(REPO)}")
    results = agent_rules.scan({"repos": [REPO]})
    for r in results:
        insert_cube(conn, result_to_cube(r))
    rebuild_fts(conn)
    print(f"   ingested {len(results)} rule-cubes (section-level)")
    for r in results[:8]:
        print(f"     - {r.metadata['heading']}")

    # 2. SNAPSHOT what the agent retrieves for a known task.
    banner(f"2. SNAPSHOT baseline for task: {TASK!r}")
    snap = capture_snapshot(conn, TASK, k=K, note="demo baseline")
    for h in snap["hits"]:
        print(f"   [{h['id'][:10]}] {h['title']}")
    if not snap["hits"]:
        print("   (no hits — task did not match; adjust TASK)")
        return
    top = snap["hits"][0]

    # 3. DRIFT: a consolidation pass kills the top rule (as happens for real
    #    when memory is merged/pruned, or the rule file is edited).
    banner("3. DRIFT — a consolidation pass kills the top-ranked rule")
    conn.execute("UPDATE glaze_cubes SET review_status='killed' WHERE id=?", (top["id"],))
    conn.execute("DELETE FROM glaze_cubes WHERE id=?", (top["id"],))
    conn.commit()
    rebuild_fts(conn)
    print(f"   killed + removed: {top['title']}")

    # 4. RE-CHECK the snapshot -> regression caught with no ground truth.
    banner("4. RE-CHECK snapshot -> regression detected")
    for res in check_all(conn):
        print(f"   task:      {res['task']!r}")
        print(f"   REGRESSED: {res['regressed']}   overlap={res['overlap']}")
        if res["dropped"]:
            print(f"   DROPPED:   {res['dropped']}")
        if res["stale"]:
            print(f"   STALE:     {res['stale']}")
        if res["added"]:
            print(f"   ADDED:     {res['added']}")
        print(f"   now top-K: {res['new_titles']}")

    print("\n-> The agent silently lost a rule it used to retrieve. Helicon "
          "caught it\n   the moment memory changed — no labels, no ground truth.\n")


if __name__ == "__main__":
    main()
