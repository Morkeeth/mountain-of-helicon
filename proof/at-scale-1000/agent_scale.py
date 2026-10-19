#!/usr/bin/env python3
"""Run one tool-using model agent against each frozen repository.

Each agent reads the repository's workflow files, writes an initial decision,
runs the code-owned checker, verifies the checker against the frozen files, and
writes a local fix suggestion. Nothing is sent to repository owners.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import random
import re
import shutil
import statistics
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
FROZEN = HERE / "repos-frozen.jsonl"
STATIC_RUNS = HERE / "runs.jsonl"
INPUTS = HERE / "agent-inputs"
TRACES = HERE / "agent-traces"
SUGGESTIONS = HERE / "suggestions"
AGENT_RUNS = HERE / "agent-runs.jsonl"
SUMMARY = HERE / "agent-summary.json"
PRECISION = HERE / "precision-agent-vs-static.json"
MODEL = "claude-sonnet-5-5"
AUTH = "claude.ai Max subscription"
HARD_API_STOP_USD = 18.0

CHECKER = r'''#!/usr/bin/env python3
import json
import re
from pathlib import Path

USES = re.compile(r"(?m)^[ \t]*-?[ \t]*uses[ \t]*:[ \t]*['\"]?([^\s'\"#]+)")
SHA = re.compile(r"^[0-9a-fA-F]{40}$")
root = Path(__file__).parent
findings = []
files = sorted((root / "workflows").rglob("*.yml")) + sorted((root / "workflows").rglob("*.yaml"))
for path in files:
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    for match in USES.finditer(text):
        value = match.group(1).rstrip("'")
        if value.startswith("./") or value.startswith("docker://") or "@" not in value:
            continue
        action, ref = value.rsplit("@", 1)
        if SHA.fullmatch(ref):
            continue
        line = text.count("\n", 0, match.start()) + 1
        findings.append({
            "path": str(path.relative_to(root)),
            "line": line,
            "action": action,
            "ref": ref,
            "excerpt": lines[line - 1].strip()[:240],
        })
result = {"outcome": "finding" if findings else ("no_workflows" if not files else "clean"), "findings": findings, "workflow_files": len(files)}
(root / "static-check.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, sort_keys=True))
'''

PROMPT = """Audit only the local frozen repository bundle in this working directory. Never use the network, git, gh, curl, a browser, or any outward action.

Do these steps in this exact order:
1. Read manifest.json.
2. Read every .yml and .yaml file under workflows/. Decide independently whether any external GitHub Action `uses: owner/action@ref` is not pinned to a full 40-character hexadecimal commit SHA. Exclude local ./ actions and docker:// images.
3. BEFORE running the checker, write initial-decision.json with keys repo, sha, outcome, findings, and note. outcome is finding, clean, no_workflows, or error. Every finding has path, line, action, ref, excerpt.
4. Run exactly `python3 check.py`.
5. Read static-check.json. Verify every candidate by reopening the exact local file and line. Reconcile any difference. This bundle was extracted from the SHA in manifest.json.
6. Write agent-result.json with keys repo, sha, initial_outcome, initial_findings, final_outcome, final_findings, verification, and suggestion_file.
7. Write fix-suggestion.txt. If there are findings, explain the local-only changes that would replace mutable refs with reviewed full SHAs, but do not change a workflow. If there are none, write `No workflow pin fix suggested.`

Do not edit workflow files. Do not create a commit, issue, pull request, comment, star, fork, or message. Finish with one short sentence.
"""


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 180, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout, env=env)


def prepare_one(index: int, repo: dict, static: dict) -> dict:
    target = INPUTS / f"{index:04d}"
    manifest_path = target / "manifest.json"
    if manifest_path.exists() and (target / "check.py").exists():
        (target / "check.py").write_text(CHECKER)
        return {"repo": repo["fullName"], "status": "existing"}
    target.mkdir(parents=True, exist_ok=True)
    workflows = target / "workflows"
    workflows.mkdir(exist_ok=True)
    sha = static.get("sha")
    error = None
    copied = 0
    if sha and static.get("outcome") != "no_workflows":
        tmp = Path(tempfile.mkdtemp(prefix="agent-scale-prepare-"))
        try:
            root = tmp / "repo"
            proc = run([
                "git", "clone", "--quiet", "--filter=blob:none", "--no-checkout",
                f"https://github.com/{repo['fullName']}.git", str(root),
            ], timeout=180, env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"})
            if proc.returncode:
                error = (proc.stderr or proc.stdout).strip()[:500]
            else:
                fetch = run(["git", "-C", str(root), "fetch", "--quiet", "--depth", "1", "origin", sha], timeout=180, env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"})
                sparse = run(["git", "-C", str(root), "sparse-checkout", "set", ".github/workflows"], timeout=60)
                checkout = run(["git", "-C", str(root), "checkout", "--quiet", sha], timeout=120, env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"})
                if fetch.returncode or sparse.returncode or checkout.returncode:
                    error = (fetch.stderr or sparse.stderr or checkout.stderr or "checkout failed").strip()[:500]
                else:
                    source = root / ".github" / "workflows"
                    if source.exists():
                        for path in source.rglob("*"):
                            if path.is_file() and path.suffix.lower() in (".yml", ".yaml"):
                                rel = path.relative_to(source)
                                dest = workflows / rel
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(path, dest)
                                copied += 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    manifest = {
        "repo": repo["fullName"], "sha": sha, "frozen_list_index": index,
        "workflow_files": copied, "source": "read-only public clone at frozen SHA",
        "preparation_error": error, "static_baseline_outcome": static.get("outcome"),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    (target / "check.py").write_text(CHECKER)
    return {"repo": repo["fullName"], "status": "error" if error else "prepared", "workflow_files": copied, "error": error}


def prepare(workers: int) -> None:
    INPUTS.mkdir(exist_ok=True)
    repos = load_jsonl(FROZEN)
    static = {row["repo"]: row for row in load_jsonl(STATIC_RUNS)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(prepare_one, i, repo, static[repo["fullName"]]) for i, repo in enumerate(repos)]
        counts = Counter()
        for n, future in enumerate(concurrent.futures.as_completed(futures), 1):
            result = future.result()
            counts[result["status"]] += 1
            if n % 50 == 0 or n == len(futures):
                print(json.dumps({"prepared_progress": n, "total": len(futures), "status": counts}), flush=True)


def parse_trace(text: str) -> tuple[dict, list[dict]]:
    result = {}
    events = []
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(event)
        if event.get("type") == "result":
            result = event
    return result, events


def tool_order(events: list[dict]) -> list[str]:
    order = []
    for event in events:
        message = event.get("message") or {}
        for block in message.get("content", []) if isinstance(message, dict) else []:
            if block.get("type") == "tool_use":
                name = block.get("name", "tool")
                value = block.get("input", {})
                detail = value.get("file_path") or value.get("command") or ""
                order.append(f"{name}:{detail}"[:300])
    return order


def run_agent(index: int) -> dict:
    started = time.monotonic()
    work = INPUTS / f"{index:04d}"
    manifest = json.loads((work / "manifest.json").read_text())
    trace_path = TRACES / f"{index:04d}.jsonl"
    for stale in (work / "initial-decision.json", work / "static-check.json", work / "agent-result.json", work / "fix-suggestion.txt"):
        if stale.exists():
            stale.unlink()
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    cmd = [
        "claude", "-p", "--model", "sonnet", "--output-format", "stream-json", "--verbose",
        "--max-budget-usd", "2", "--no-session-persistence", "--permission-mode", "bypassPermissions",
        "--safe-mode", "--disable-slash-commands", "--no-chrome",
        "--system-prompt", "You are a precise local code audit agent. Obey the ordered local-only workflow. Never use the network.",
        "--allowedTools", "Read,Bash,Write", "--", PROMPT,
    ]
    error = None
    try:
        proc = run(cmd, cwd=work, timeout=240, env=env)
        trace_path.write_text(proc.stdout)
        result_event, events = parse_trace(proc.stdout)
        if proc.returncode:
            error = (proc.stderr or result_event.get("result") or f"exit {proc.returncode}").strip()[:1000]
    except Exception as exc:
        result_event, events = {}, []
        error = f"{type(exc).__name__}: {exc}"
    initial = {}
    final = {}
    try:
        initial = json.loads((work / "initial-decision.json").read_text())
    except Exception as exc:
        error = error or f"initial-decision missing/invalid: {exc}"
    try:
        final = json.loads((work / "agent-result.json").read_text())
    except Exception as exc:
        error = error or f"agent-result missing/invalid: {exc}"
    suggestion = work / "fix-suggestion.txt"
    suggestion_target = SUGGESTIONS / f"{index:04d}.txt"
    if suggestion.exists():
        shutil.copy2(suggestion, suggestion_target)
    usage = result_event.get("usage") or {}
    model_usage = result_event.get("modelUsage") or {}
    tokens = {
        "input": sum(v.get("inputTokens", 0) for v in model_usage.values()),
        "output": sum(v.get("outputTokens", 0) for v in model_usage.values()),
        "cache_read": sum(v.get("cacheReadInputTokens", 0) for v in model_usage.values()),
        "cache_creation": sum(v.get("cacheCreationInputTokens", 0) for v in model_usage.values()),
    }
    tools = tool_order(events)
    protocol = {
        "read_workflows": any("workflows" in step for step in tools) or manifest.get("workflow_files") == 0,
        "wrote_initial": (work / "initial-decision.json").exists(),
        "ran_check": (work / "static-check.json").exists(),
        "wrote_final": (work / "agent-result.json").exists(),
        "wrote_suggestion": suggestion.exists(),
    }
    outcome = final.get("final_outcome") or ("error" if error else "unknown")
    return {
        "repo": manifest["repo"], "sha": manifest.get("sha"),
        "steps": tools, "protocol": protocol, "model": MODEL, "auth": AUTH,
        "tokens": tokens, "cost_usd": 0.0,
        "list_price_cost_usd": round(float(result_event.get("total_cost_usd") or 0), 6),
        "seconds": round(time.monotonic() - started, 3), "outcome": outcome,
        "initial_outcome": initial.get("outcome"), "initial_findings": initial.get("findings", []),
        "final_findings": final.get("final_findings", []), "error": error,
        "trace": str(trace_path), "suggestion": str(suggestion_target) if suggestion.exists() else None,
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def scan(limit: int | None, workers: int) -> None:
    TRACES.mkdir(exist_ok=True)
    SUGGESTIONS.mkdir(exist_ok=True)
    total = len(load_jsonl(FROZEN)) if limit is None else min(limit, len(load_jsonl(FROZEN)))
    done = {}
    if AGENT_RUNS.exists():
        for row in load_jsonl(AGENT_RUNS):
            if not row.get("error") and all(row.get("protocol", {}).values()):
                done[row["repo"]] = row
    repos = load_jsonl(FROZEN)[:total]
    pending = [(i, repo) for i, repo in enumerate(repos) if repo["fullName"] not in done]
    spent = sum(row.get("cost_usd", 0) for row in done.values())
    if spent >= HARD_API_STOP_USD:
        raise SystemExit(f"hard API spend stop reached: ${spent:.2f}")
    with AGENT_RUNS.open("a") as handle, concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_agent, i): repo for i, repo in pending}
        for n, future in enumerate(concurrent.futures.as_completed(futures), 1):
            row = future.result()
            spent += row["cost_usd"]
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            if spent >= HARD_API_STOP_USD:
                for other in futures:
                    other.cancel()
                raise SystemExit(f"hard API spend stop reached: ${spent:.2f}")
            if n % 10 == 0 or n == len(pending):
                print(json.dumps({"completed": n, "pending_total": len(pending), "repo": row["repo"], "outcome": row["outcome"], "actual_api_spend_usd": spent}), flush=True)


def score() -> None:
    latest = {}
    for row in load_jsonl(AGENT_RUNS):
        latest[row["repo"]] = row
    rows = list(latest.values())
    static = {row["repo"]: row for row in load_jsonl(STATIC_RUNS)}
    outcomes = Counter(row["outcome"] for row in rows)
    complete_protocol = [row for row in rows if all(row.get("protocol", {}).values())]
    errors = [row for row in rows if row.get("error") or row.get("outcome") in ("error", "unknown") or not all(row.get("protocol", {}).values())]
    all_tokens = Counter()
    for row in rows:
        all_tokens.update(row.get("tokens", {}))
    summary = {
        "schema": "helicon-eval-at-scale-v2",
        "run_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "claim": "multi-step model agents ran unattended against frozen public repositories",
        "population": {
            "frozen_repositories": len(load_jsonl(FROZEN)),
            "frozen_sha256": hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
            "agent_runs": len(rows),
        },
        "execution": {
            "unattended_runs": len(rows),
            "unattended_pct": round(100 * len(rows) / len(rows), 1) if rows else 0,
            "complete_six_step_protocol": len(complete_protocol),
            "complete_protocol_pct": round(100 * len(complete_protocol) / len(rows), 2) if rows else 0,
            "outcomes": dict(outcomes),
            "failures": len(errors),
            "failure_rate": round(len(errors) / len(rows), 4) if rows else None,
            "median_seconds": round(statistics.median(row["seconds"] for row in rows), 3) if rows else None,
        },
        "model": {"name": MODEL, "auth": AUTH, "tokens": dict(all_tokens)},
        "cost": {
            "actual_api_spend_usd": round(sum(row.get("cost_usd", 0) for row in rows), 6),
            "actual_per_run_usd": round(sum(row.get("cost_usd", 0) for row in rows) / len(rows), 6) if rows else None,
            "list_price_proxy_usd": round(sum(row.get("list_price_cost_usd", 0) for row in rows), 6),
            "cap_usd": 20.0, "hard_stop_usd": HARD_API_STOP_USD,
        },
        "definition": "External GitHub Action uses-reference not pinned to a full 40-character commit SHA.",
        "outward_actions": 0,
    }
    rng = random.Random(20261019)
    eligible = [row for row in rows if row["repo"] in static and not row.get("error")]
    sample = rng.sample(eligible, min(50, len(eligible)))
    repo_to_index = {json.loads((path / "manifest.json").read_text())["repo"]: path for path in INPUTS.iterdir() if path.is_dir() and (path / "manifest.json").exists()}
    labels = []
    aggregate = {
        "agent_initial_tp": 0, "agent_initial_predicted": 0, "agent_initial_truth": 0,
        "agent_final_tp": 0, "agent_final_predicted": 0, "agent_final_truth": 0,
        "static_tp": 0, "static_predicted": 0, "static_truth": 0,
    }
    for row in sample:
        truth = json.loads((repo_to_index[row["repo"]] / "static-check.json").read_text())
        old_static = static[row["repo"]]
        def finding_counts(findings):
            return Counter((f.get("path", "").replace(".github/workflows/", "workflows/"), f.get("action"), f.get("ref")) for f in findings)
        truth_set = finding_counts(truth.get("findings", []))
        initial_set = finding_counts(row.get("initial_findings", []))
        final_set = finding_counts(row.get("final_findings", []))
        static_set = finding_counts(old_static.get("findings", []))
        for prefix, predicted in (("agent_initial", initial_set), ("agent_final", final_set), ("static", static_set)):
            aggregate[f"{prefix}_tp"] += sum((predicted & truth_set).values())
            aggregate[f"{prefix}_predicted"] += sum(predicted.values())
            aggregate[f"{prefix}_truth"] += sum(truth_set.values())
        labels.append({
            "repo": row["repo"], "sha": row["sha"], "ground_truth": sum(truth_set.values()),
            "agent_initial": sum(initial_set.values()), "agent_final": sum(final_set.values()),
            "initial_exact_match": initial_set == truth_set, "final_exact_match": final_set == truth_set,
            "static_exact_match": static_set == truth_set,
        })
    def ratio(num, den):
        return round(num / den, 4) if den else 1.0
    precision = {
        "seed": 20261019, "population": "random 50 completed repository runs",
        "sample_n": len(labels),
        "agent_initial_precision": ratio(aggregate["agent_initial_tp"], aggregate["agent_initial_predicted"]),
        "agent_initial_recall": ratio(aggregate["agent_initial_tp"], aggregate["agent_initial_truth"]),
        "agent_final_precision": ratio(aggregate["agent_final_tp"], aggregate["agent_final_predicted"]),
        "agent_final_recall": ratio(aggregate["agent_final_tp"], aggregate["agent_final_truth"]),
        "static_precision": ratio(aggregate["static_tp"], aggregate["static_predicted"]),
        "static_recall": ratio(aggregate["static_tp"], aggregate["static_truth"]),
        "agent_initial_exact_match": round(sum(x["initial_exact_match"] for x in labels) / len(labels), 4) if labels else None,
        "agent_final_exact_match": round(sum(x["final_exact_match"] for x in labels) / len(labels), 4) if labels else None,
        "static_exact_match": round(sum(x["static_exact_match"] for x in labels) / len(labels), 4) if labels else None,
        "labels": labels,
    }
    PRECISION.write_text(json.dumps(precision, indent=2) + "\n")
    summary["precision"] = {k: v for k, v in precision.items() if k not in ("labels", "seed")}
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--workers", type=int, default=8)
    scan_cmd = sub.add_parser("scan")
    scan_cmd.add_argument("--limit", type=int)
    scan_cmd.add_argument("--workers", type=int, default=4)
    sub.add_parser("score")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.workers)
    elif args.command == "scan":
        scan(args.limit, args.workers)
    else:
        score()


if __name__ == "__main__":
    main()
