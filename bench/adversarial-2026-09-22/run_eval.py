#!/usr/bin/env python3
"""Adversarial real-agent eval: stale vs corrected vs absent CLAUDE.md.

Subcommands:
  selfcheck            prove each grader goes red on the trap and green on the reference
  run [--reps N] [--only CASE] [--conds a,b] [--tag T]
  summarize --tag T    rebuild the summary from saved results

Graders never import or call Helicon. See PREREG.md.
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures"
OUT = Path(os.environ.get(
    "EVAL_OUT", Path.home() / ".local/state/day-run/2026-09-22/helicon-adversarial-eval"))
RUNS = Path(os.environ.get("EVAL_RUNS", OUT / "runs"))

MODEL = "claude-sonnet-5"
TOOLS = "Read,Edit,Write,Glob,Grep,Bash"
PER_RUN_CAP = 1.00
TOTAL_CAP = 15.00
TIMEOUT_S = 420
CASES = ["c1_renamed_function", "c2_wrong_test_command", "c3_removed_flag"]
CONDS = ["original", "corrected", "no_context"]


def sh(cmd, cwd=None, env=None, timeout=120):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def make_copy(case, cond, dest):
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(FIX / case / "repo", dest)
    if cond in ("original", "corrected"):
        shutil.copy(FIX / case / f"CLAUDE.{cond}.md", dest / "CLAUDE.md")
    sh(["git", "init", "-q", "."], cwd=dest)
    sh(["git", "add", "-A"], cwd=dest)
    sh(["git", "-c", "user.email=eval@local", "-c", "user.name=eval",
        "commit", "-qm", "fixture"], cwd=dest)


def tree_hash(path):
    h = hashlib.sha256()
    for p in sorted(Path(path).rglob("*")):
        if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts:
            h.update(str(p.relative_to(path)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def grade(case, repo):
    """Hidden grader. Independent of Helicon. Returns dict."""
    repo = Path(repo)
    res = {}
    tmp = repo.parent / "grader"
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(FIX / case / "grader", tmp)
    env = dict(os.environ, PYTHONPATH=str(repo), EVAL_REPO=str(repo), PYTHONDONTWRITEBYTECODE="1")
    if case == "c2_wrong_test_command":
        orig_tests = FIX / case / "repo" / "tests"
        res["tests_unchanged"] = tree_hash(orig_tests) == tree_hash(repo / "tests")
        # grade against the pristine tests, so an edited test cannot pass the grader
        pristine = repo.parent / "pristine_tests"
        if pristine.exists():
            shutil.rmtree(pristine)
        shutil.copytree(orig_tests, pristine)
        full = sh([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(pristine)],
                  cwd=repo, env=env)
        res["full_suite_rc"] = full.returncode
    if case == "c3_removed_flag":
        res["cli_unchanged"] = (FIX / case / "repo/ingest/cli.py").read_bytes() == \
            (repo / "ingest/cli.py").read_bytes() if (repo / "ingest/cli.py").exists() else False
    hid = sh([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
              str(tmp / "test_hidden.py")], cwd=tmp, env=env)
    res["hidden_rc"] = hid.returncode
    res["hidden_tail"] = hid.stdout.strip().splitlines()[-1:] if hid.stdout else []
    ok = hid.returncode == 0
    if case == "c2_wrong_test_command":
        ok = ok and res["full_suite_rc"] == 0 and res["tests_unchanged"]
    if case == "c3_removed_flag":
        ok = ok and res["cli_unchanged"]
    res["pass"] = ok
    return res


def stale_signal(case, repo, bash_cmds):
    """Pre-registered secondary metric: did the agent act on the stale claim?"""
    repo = Path(repo)
    if case == "c1_renamed_function":
        p = repo / "shop/checkout.py"
        src = p.read_text() if p.exists() else ""
        return {"uses_compute_total": "compute_total" in src,
                "uses_calc_total": "calc_total" in src,
                "stale_followed": "compute_total" in src}
    if case == "c2_wrong_test_command":
        pyt = [c for c in bash_cmds if "pytest" in c]
        narrow = [c for c in pyt if "tests/unit" in c]
        broad = [c for c in pyt if "tests/unit" not in c]
        return {"pytest_cmds": pyt, "ran_narrow": bool(narrow), "ran_broad": bool(broad),
                "stale_followed": bool(narrow) and not broad}
    if case == "c3_removed_flag":
        p = repo / "scripts/check_data.sh"
        src = p.read_text() if p.exists() else ""
        return {"script_exists": p.exists(), "has_strict_flag": "--strict" in src,
                "has_validate": "--validate" in src,
                "stale_followed": "--strict" in src and "--validate" not in src}
    return {}


def selfcheck():
    """Each grader must go red on the trap and green on the reference fix."""
    base = RUNS.parent / "selfcheck"
    rows = []
    plan = {
        "c1_renamed_function": [("unfixed", None), ("trap", ("trap_checkout.py", "shop/checkout.py")),
                                ("reference", ("checkout.py", "shop/checkout.py"))],
        "c2_wrong_test_command": [("unfixed", None), ("reference", ("slug.py", "textkit/slug.py"))],
        "c3_removed_flag": [("unfixed", None), ("trap", ("trap_check_data.sh", "scripts/check_data.sh")),
                            ("reference", ("check_data.sh", "scripts/check_data.sh"))],
    }
    for case, variants in plan.items():
        for name, patch in variants:
            d = base / case / name / "repo"
            make_copy(case, "no_context", d)
            if patch:
                shutil.copy(FIX / case / "reference" / patch[0], d / patch[1])
            g = grade(case, d)
            expect = name == "reference"
            rows.append((case, name, g["pass"], expect))
            print(f"{case:24s} {name:10s} pass={g['pass']!s:5s} expected={expect}")
    bad = [r for r in rows if r[2] != r[3]]
    print("SELFCHECK", "OK" if not bad else f"FAILED {bad}")
    return 0 if not bad else 1


class Budget:
    def __init__(self, cap):
        self.cap, self.spent, self.inflight = cap, 0.0, 0
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            if self.spent + (self.inflight + 1) * PER_RUN_CAP > self.cap:
                return False
            self.inflight += 1
            return True

    def release(self, cost):
        with self.lock:
            self.inflight -= 1
            self.spent += cost


def run_one(case, cond, rep, tag, budget):
    cell = RUNS / tag / case / cond / f"r{rep}"
    if not budget.acquire():
        return {"case": case, "cond": cond, "rep": rep, "skipped": "budget"}
    repo = cell / "repo"
    make_copy(case, cond, repo)
    task = (FIX / case / "task.txt").read_text().strip()
    cmd = ["claude", "-p", task, "--model", MODEL, "--setting-sources", "project",
           "--strict-mcp-config", "--tools", TOOLS, "--permission-mode", "bypassPermissions",
           "--max-budget-usd", f"{PER_RUN_CAP:.2f}", "--output-format", "stream-json",
           "--verbose", "--no-session-persistence"]
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    t0 = time.time()
    timed_out = False
    try:
        p = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True, timeout=TIMEOUT_S)
        stdout, rc = p.stdout, p.returncode
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        rc, timed_out = None, True
    wall = time.time() - t0
    (cell / "stream.jsonl").write_text(stdout)
    result, bash_cmds, init = {}, [], {}
    for line in stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            init = {"model": ev.get("model"), "tools": ev.get("tools"),
                    "claude_code_version": ev.get("claude_code_version")}
        if ev.get("type") == "assistant":
            for blk in ev.get("message", {}).get("content", []):
                if blk.get("type") == "tool_use" and blk.get("name") == "Bash":
                    bash_cmds.append(blk.get("input", {}).get("command", ""))
        if ev.get("type") == "result":
            result = ev
    cost = result.get("total_cost_usd")
    budget.release(cost if cost is not None else PER_RUN_CAP)
    row = {
        "case": case, "cond": cond, "rep": rep, "rc": rc, "timed_out": timed_out,
        "wall_s": round(wall, 1), "duration_ms": result.get("duration_ms"),
        "num_turns": result.get("num_turns"), "cost_usd": cost,
        "cost_counted": cost if cost is not None else PER_RUN_CAP,
        "is_error": result.get("is_error"), "subtype": result.get("subtype"),
        "final_text": (result.get("result") or "")[:600], "init": init,
        "grade": grade(case, repo), "stale": stale_signal(case, repo, bash_cmds),
        "bash_cmds": bash_cmds,
    }
    (cell / "row.json").write_text(json.dumps(row, indent=1))
    print(f"{case:24s} {cond:10s} r{rep} pass={row['grade']['pass']!s:5s} "
          f"stale={row['stale'].get('stale_followed')!s:5s} ${cost} {row['wall_s']}s", flush=True)
    return row


def summarize(tag):
    rows = [json.loads(p.read_text()) for p in sorted((RUNS / tag).rglob("row.json"))]
    table = {}
    for r in rows:
        k = (r["case"], r["cond"])
        t = table.setdefault(k, {"n": 0, "pass": 0, "stale": 0, "cost": 0.0, "wall": []})
        t["n"] += 1
        t["pass"] += int(r["grade"]["pass"])
        t["stale"] += int(bool(r["stale"].get("stale_followed")))
        t["cost"] += r["cost_counted"]
        t["wall"].append(r["wall_s"])
    summ = {"tag": tag, "total_cost_counted": round(sum(r["cost_counted"] for r in rows), 4),
            "cells": {f"{c}|{d}": {**v, "cost": round(v["cost"], 4),
                                   "median_wall_s": sorted(v["wall"])[len(v["wall"]) // 2]}
                      for (c, d), v in sorted(table.items())}}
    (RUNS / tag / "summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))
    return summ


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["selfcheck", "run", "summarize"])
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--only", default="")
    ap.add_argument("--conds", default=",".join(CONDS))
    ap.add_argument("--tag", default="grid")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--spent", type=float, default=0.0, help="spend already used by earlier runs")
    a = ap.parse_args()
    if a.cmd == "selfcheck":
        return selfcheck()
    if a.cmd == "summarize":
        summarize(a.tag)
        return 0
    cases = [a.only] if a.only else CASES
    conds = a.conds.split(",")
    jobs = [(c, d, r) for r in range(1, a.reps + 1) for c in cases for d in conds]
    budget = Budget(TOTAL_CAP - a.spent)
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(lambda j: run_one(*j, a.tag, budget), jobs))
    summarize(a.tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
