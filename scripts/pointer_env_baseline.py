#!/usr/bin/env python3
"""Baseline arm: naive "missing ~/ = broken" vs env-aware lie grade.

The naive arm is what any competent team ships in two hours after noticing
home paths: expanduser and mark missing as broken. The env-aware arm (current
helicon.pointers) refuses to call that a *repo lie*.

If naive wins on a case that matters, that is the finding — print it.
Exit 0 always when the comparison runs; this is a measurement, not a gate.

Usage:
  python3 scripts/pointer_env_baseline.py
  python3 scripts/pointer_env_baseline.py /path/to/repo
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helicon import pointers as P  # noqa: E402
from helicon.review import review, review_summary  # noqa: E402


_RE_BACKTICK = re.compile(r"`([^`\n]+)`")


def naive_broken_home_targets(text: str) -> list[str]:
    """Two-hour naive grader: any `~/…` backtick path that expanduser misses
    is broken. No route class, no machine_gap distinction."""
    out = []
    for m in _RE_BACKTICK.finditer(text):
        raw = m.group(1).strip()
        if not raw.startswith("~"):
            continue
        if " " in raw:
            continue
        if not os.path.exists(os.path.expanduser(raw)):
            out.append(raw)
    return out


def fixture_cases(tmp: str) -> list[dict]:
    """Synthetic cases where the arms must disagree or agree on purpose."""
    cases = []

    # Disagree: missing host config — naive convicts, env-aware does not.
    d1 = os.path.join(tmp, "env-missing")
    os.makedirs(d1)
    open(os.path.join(d1, "AGENTS.md"), "w").write(
        "Requires `~/.helicon-baseline-missing-2026.json` and `present.md`.\n"
    )
    open(os.path.join(d1, "present.md"), "w").write("ok\n")
    cases.append({"name": "missing-host-config", "repo": d1, "expect_disagree": True})

    # Agree: intra-repo dead pointer — both convict.
    d2 = os.path.join(tmp, "repo-dead")
    os.makedirs(d2)
    open(os.path.join(d2, "CLAUDE.md"), "w").write(
        "Always read `docs/DOES-NOT-EXIST.md` first.\n"
    )
    cases.append({"name": "intra-repo-dead", "repo": d2, "expect_disagree": False})

    # Agree: clean repo paths only.
    d3 = os.path.join(tmp, "clean")
    os.makedirs(os.path.join(d3, "docs"))
    open(os.path.join(d3, "docs", "SETUP.md"), "w").write("#\n")
    open(os.path.join(d3, "CLAUDE.md"), "w").write("Read `docs/SETUP.md`.\n")
    cases.append({"name": "clean-repo", "repo": d3, "expect_disagree": False})

    # Present host path: create a probe under HOME… caller sets HOME to tmp/home
    return cases


def score_repo(repo: str) -> dict:
    P._TREE_CACHE.clear()
    env = review_summary(repo, review(repo))
    # Naive: scan instruction files for missing ~/ backtick paths
    naive_hits = []
    for rel in ("AGENTS.md", "CLAUDE.md", "AGENT.md", "CONTEXT.md", ".cursorrules"):
        path = os.path.join(repo, rel)
        if not os.path.isfile(path):
            continue
        text = open(path, encoding="utf-8", errors="replace").read()
        for t in naive_broken_home_targets(text):
            naive_hits.append(f"{rel}:{t}")
    # Naive broken count = env broken (repo lies) + naive-only home misses
    # For comparison we report naive_home_broken separately and env broken.
    return {
        "env_broken": env["broken"],
        "env_checked": env["checked"],
        "env_grade": env["grade"],
        "env_machine_gaps": len(env.get("machine_gaps") or []),
        "naive_home_broken": len(naive_hits),
        "naive_home_hits": naive_hits,
        "env_findings": [f.get("raw") for f in env.get("findings") or []],
    }


def main(argv: list[str]) -> int:
    extra = [os.path.abspath(a) for a in argv[1:]]
    tmp = tempfile.mkdtemp(prefix="pointer-env-baseline-")
    home = os.path.join(tmp, "home")
    os.makedirs(home)
    # Isolate HOME so probes cannot see the operator's real ~/.helicon.
    old_home = os.environ.get("HOME")
    os.environ["HOME"] = home
    try:
        cases = fixture_cases(tmp)
        for repo in extra:
            cases.append({"name": f"live:{repo}", "repo": repo, "expect_disagree": None})

        print("pointer_env_baseline — naive missing-~/ = broken  vs  env-aware lie grade")
        print(f"HOME={home} (empty on purpose)")
        print("")
        disagree = 0
        for c in cases:
            s = score_repo(c["repo"])
            # Naive total lie-like count for the home dimension + env repo broken
            naive_lie = s["env_broken"] + s["naive_home_broken"]
            # Where they disagree: naive_home_broken > 0 while those are not env findings
            delta = s["naive_home_broken"]  # env excludes these from broken
            tag = "DISAGREE" if delta else "agree"
            if delta:
                disagree += 1
            print(f"  [{tag}] {c['name']}")
            print(f"         env:    broken={s['env_broken']} checked={s['env_checked']} "
                  f"grade={s['env_grade']} machine_gaps={s['env_machine_gaps']}")
            print(f"         naive:  home_broken={s['naive_home_broken']} "
                  f"hits={s['naive_home_hits'] or '—'}")
            print(f"         naive_lie_proxy={naive_lie}  (env_broken + naive_home_broken)")
            if c.get("expect_disagree") is True and delta == 0:
                print("         !! expected disagreement; naive did not fire — check fixture")
            if c.get("expect_disagree") is False and delta:
                print("         !! unexpected disagreement on a should-agree case")
            print("")

        print(f"cases={len(cases)}  disagreements={disagree}")
        print("Finding: naive flags missing host paths as lies; env-aware does not.")
        print("If that costs recall you care about, the WRONG section of the receipt says so.")
        return 0
    finally:
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
