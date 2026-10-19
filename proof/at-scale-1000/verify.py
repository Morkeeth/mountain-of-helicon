#!/usr/bin/env python3
"""Check the published numbers in agent-summary.json against the rows in this folder.

Standard library only. Exit 0 when every check passes, 1 when one fails.
Run from anywhere: python3 proof/at-scale-1000/verify.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    summary = json.loads((HERE / "agent-summary.json").read_text())
    failures = []

    def check(name, got, want):
        ok = got == want
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {got} (summary says {want})")
        if not ok:
            failures.append(name)

    frozen = HERE / "repos-frozen.jsonl"
    check("frozen list sha256", hashlib.sha256(frozen.read_bytes()).hexdigest(),
          summary["population"]["frozen_sha256"])
    repos = load_jsonl(frozen)
    check("frozen repositories", len(repos), summary["population"]["frozen_repositories"])

    # The last row per repository wins, as in agent_scale.py score(): retries append rows.
    latest = {}
    for row in load_jsonl(HERE / "agent-runs-public.jsonl"):
        latest[row["repo"]] = row
    rows = list(latest.values())
    check("agent runs", len(rows), summary["population"]["agent_runs"])
    check("every run is a frozen repository", set(latest) <= {r["fullName"] for r in repos}, True)
    check("outcomes", dict(Counter(r["outcome"] for r in rows)), summary["execution"]["outcomes"])
    complete = sum(1 for r in rows if all((r.get("protocol") or {}).values()))
    check("complete six-step protocol", complete, summary["execution"]["complete_six_step_protocol"])
    tokens = Counter()
    for r in rows:
        tokens.update(r.get("tokens") or {})
    check("output tokens", tokens["output"], summary["model"]["tokens"]["output"])
    check("api spend usd", round(sum(r.get("cost_usd") or 0 for r in rows), 6),
          summary["cost"]["actual_api_spend_usd"])

    print("all checks pass" if not failures else f"{len(failures)} check(s) failed: {', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
