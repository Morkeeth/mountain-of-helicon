"""Demo: catch REAL agent-memory drift from a repo's own git history.

This is the honest version of the regression demo. The drift is NOT scripted
(no hand-deleting the row we just snapshotted). Instead we replay a repo's
CLAUDE.md across its REAL commit history:

  1. Ingest the repo's agent rules as they existed at an OLD commit.
  2. Snapshot what the agent retrieves for a known task (the baseline).
  3. Re-ingest the SAME file as it exists at HEAD — the human edited it in
     between (real commits, real diff).
  4. Re-check the snapshot -> the regression is whatever the real edit did to
     retrieval. No ground truth, no staging.

Reproducible by any judge: it runs on this repo's own committed CLAUDE.md.

Run:  python3 scripts/demo_realdrift.py
      DEMO_REPO=~/CODE/other DEMO_TASK="..." python3 scripts/demo_realdrift.py
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from glaze.connectors import agent_rules
from glaze.scanner import result_to_cube
from glaze.db import init_db, insert_cube, rebuild_fts
from glaze.snapshots import capture_snapshot, check_all

REPO = os.path.expanduser(os.environ.get("DEMO_REPO", "~/CODE/glaze"))
RULES_FILE = os.environ.get("DEMO_RULES_FILE", "CLAUDE.md")
TASK = os.environ.get("DEMO_TASK", "what memory sources does layer 1 extract from")
K = 3


def banner(msg):
    print(f"\n{'='*68}\n{msg}\n{'='*68}")


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def file_history(repo, path):
    """Commits that touched `path`, oldest first: [(sha, subject), ...]."""
    out = git(repo, "log", "--reverse", "--follow", "--format=%h\t%s", "--", path).stdout
    rows = [ln.split("\t", 1) for ln in out.splitlines() if "\t" in ln]
    return rows


def materialize(repo, ref, path, dest_repo_dir):
    """Write `path` as it existed at `ref` into dest_repo_dir/<path>."""
    content = git(repo, "show", f"{ref}:{path}").stdout
    target = os.path.join(dest_repo_dir, path)
    os.makedirs(os.path.dirname(target) or dest_repo_dir, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def ingest_rules_version(conn, repo_name, work_root, repo_src, ref, path):
    """Ingest `path` as of `ref`. Identity is by content_hash (UNIQUE): a section
    whose text is unchanged is skipped (its cube + id persist); only a genuinely
    edited section becomes a new cube. No deletes — the snapshot diff, not this
    function, decides what drifted."""
    repo_dir = os.path.join(work_root, repo_name)
    os.makedirs(repo_dir, exist_ok=True)
    materialize(repo_src, ref, path, repo_dir)
    results = agent_rules.scan({"repos": [repo_dir]})
    inserted = 0
    for r in results:
        if insert_cube(conn, result_to_cube(r)):
            inserted += 1
    rebuild_fts(conn)
    return results, inserted


def main():
    hist = file_history(REPO, RULES_FILE)
    if len(hist) < 2:
        print(f"Need >=2 commits touching {RULES_FILE} in {REPO}; found {len(hist)}.")
        print("Point DEMO_REPO at a repo whose agent-rules file has real history.")
        return
    old_sha, old_subj = hist[0]
    new_sha, new_subj = hist[-1]
    repo_name = os.path.basename(os.path.normpath(REPO))

    db_path = os.path.join(tempfile.mkdtemp(prefix="helicon-realdrift-"), "demo.db")
    conn = init_db(db_path)
    work_root = tempfile.mkdtemp(prefix="helicon-worktree-")

    banner(f"1. INGEST {repo_name}/{RULES_FILE} @ OLD commit {old_sha}  ({old_subj[:44]})")
    old_results, _ = ingest_rules_version(conn, repo_name, work_root, REPO, old_sha, RULES_FILE)
    print(f"   {len(old_results)} rule-cubes at {old_sha}")

    banner(f"2. SNAPSHOT baseline for task: {TASK!r}")
    snap = capture_snapshot(conn, TASK, k=K, note=f"baseline @ {old_sha}")
    if not snap["hits"]:
        print("   (no hits — pick a DEMO_TASK that matches a section in the file)")
        return
    for h in snap["hits"]:
        print(f"   [{h['id'][:10]}] {h['title']}")

    banner(f"3. REAL DRIFT — replay history to HEAD {new_sha}  ({new_subj[:44]})")
    n_commits = len(hist)
    print(f"   {RULES_FILE} was edited across {n_commits} real commits between "
          f"{old_sha} and {new_sha}.")
    new_results, new_inserted = ingest_rules_version(conn, repo_name, work_root, REPO, new_sha, RULES_FILE)
    print(f"   {len(new_results)} rule-cubes at {new_sha}; {new_inserted} are NEW "
          f"(edited sections), {len(new_results) - new_inserted} unchanged (same content_hash)")

    banner("4. RE-CHECK snapshot -> regression is whatever the real edits caused")
    any_reg = False
    for res in check_all(conn):
        any_reg = any_reg or res["regressed"]
        print(f"   task:      {res['task']!r}")
        print(f"   REGRESSED: {res['regressed']}   overlap={res['overlap']}")
        if res["dropped"]:
            print(f"   DROPPED:   {res['dropped']}")
        if res["stale"]:
            print(f"   STALE:     {res['stale']}")
        if res["added"]:
            print(f"   ADDED:     {res['added']}")
        print(f"   now top-K: {res['new_titles']}")

    if any_reg:
        print("\n-> The agent's retrieved context for this task changed because a human "
              "edited\n   the rules file. Helicon caught it from real git history — no "
              "staging, no labels.")
        # Honest finding: a re-scan does not retire the superseded section, so the
        # old and edited versions of an edited rule can both linger and retrieve.
        titles = [t for res in check_all(conn) for t in res["new_titles"]]
        dupes = sorted({t for t in titles if titles.count(t) > 1})
        if dupes:
            print("\n   NOTE (real gap): re-scan left stale duplicates in the top-K "
                  f"{dupes} —\n   the old section wasn't reconciled. Same failure class as "
                  "unreconciled\n   cross-session memory; the battery's Redundancy/Freshness "
                  "tests flag it.\n")
    else:
        print("\n-> No retrieval change for this task across the real history. Try a "
              "DEMO_TASK\n   that touches a section the commits actually edited.\n")


if __name__ == "__main__":
    main()
