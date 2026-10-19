#!/usr/bin/env python3
"""Freeze 1,000 public repositories and check GitHub Actions supply-chain pins.

The check is deterministic. A finding is an external ``uses: owner/action@ref``
reference whose ref is not a full 40-character hexadecimal commit SHA. Local
actions (``./``) and Docker images are outside the population.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPOS = HERE / "repos-frozen.jsonl"
RUNS = HERE / "runs.jsonl"
SUMMARY = HERE / "summary.json"
LABELS = HERE / "precision-sample.json"
LANGUAGES = ["Python", "JavaScript", "TypeScript", "Go", "Rust", "Java", "C++", "Ruby", "PHP", "C#"]
SIZE_RANGE = (0, 200_000)
USES_RE = re.compile(r"(?m)^[ \t]*-?[ \t]*uses[ \t]*:[ \t]*['\"]?([^\s'\"#]+)")
FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def run(cmd: list[str], timeout: int = 60, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, env=env)


def gh_json(args: list[str], retries: int = 2) -> tuple[object | None, str | None]:
    last = ""
    for attempt in range(retries + 1):
        try:
            proc = run(["gh", *args], timeout=90)
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
        else:
            if proc.returncode == 0:
                try:
                    return json.loads(proc.stdout), None
                except json.JSONDecodeError as exc:
                    last = f"JSONDecodeError: {exc}"
            else:
                last = (proc.stderr or proc.stdout).strip()[:500]
        if attempt < retries:
            time.sleep(0.4 * (attempt + 1))
    return None, last


def freeze() -> None:
    if REPOS.exists():
        raise SystemExit(f"refusing to replace frozen list: {REPOS}")
    rows: list[dict] = []
    low, high = SIZE_RANGE
    for language in LANGUAGES:
        proc = run([
            "gh", "search", "repos", "--language", language,
            "--size", f"{low}..{high}", "--archived=false",
            "--include-forks=false", "--visibility=public",
            "--sort", "updated", "--order", "desc", "--limit", "100",
            "--json", "fullName,defaultBranch,language,size,stargazersCount,updatedAt,url",
        ], timeout=120)
        if proc.returncode:
            raise SystemExit(proc.stderr)
        found = json.loads(proc.stdout)
        if len(found) != 100:
            raise SystemExit(f"{language}: expected 100, got {len(found)}")
        for item in found:
            item["stratum"] = language
            item["frozen_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            rows.append(item)
        time.sleep(10)
    names = [row["fullName"] for row in rows]
    if len(rows) != 1_000 or len(set(names)) != 1_000:
        raise SystemExit(f"expected 1000 unique repositories, got rows={len(rows)} unique={len(set(names))}")
    with REPOS.open("x") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    digest = hashlib.sha256(REPOS.read_bytes()).hexdigest()
    print(json.dumps({"repos": len(rows), "sha256": digest, "path": str(REPOS)}))


def api_path(repo: str, suffix: str) -> str:
    return f"repos/{repo}/{suffix}"


def check_repo(repo: dict) -> dict:
    started = time.monotonic()
    name = repo["fullName"]
    branch = repo["defaultBranch"] or "HEAD"
    steps = ["sparse_clone"]
    tmp = Path(tempfile.mkdtemp(prefix="at-scale-pin-"))
    try:
        clone_error = ""
        for attempt in range(3):
            proc = run([
                "git", "clone", "--quiet", "--filter=blob:none", "--no-checkout",
                "--depth", "1", "--single-branch", "--branch", branch,
                f"https://github.com/{name}.git", str(tmp / "repo"),
            ], timeout=120, env_extra={"GIT_LFS_SKIP_SMUDGE": "1"})
            if proc.returncode == 0:
                break
            clone_error = (proc.stderr or proc.stdout).strip()[:500]
            shutil.rmtree(tmp / "repo", ignore_errors=True)
            time.sleep(0.5 * (attempt + 1))
        else:
            return make_row(repo, None, steps, "error", clone_error or "clone failed", [], started)
        root = tmp / "repo"
        steps.append("resolve_sha")
        sha_proc = run(["git", "-C", str(root), "rev-parse", "HEAD"])
        sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else None
        steps.append("checkout_workflows")
        sparse = run(["git", "-C", str(root), "sparse-checkout", "set", ".github/workflows"], env_extra={"GIT_LFS_SKIP_SMUDGE": "1"})
        checkout = run([
            "git", "-C", str(root), "-c", "filter.lfs.smudge=",
            "-c", "filter.lfs.required=false", "checkout", "--quiet",
        ], env_extra={"GIT_LFS_SKIP_SMUDGE": "1"})
        if sparse.returncode or checkout.returncode:
            err = (sparse.stderr or checkout.stderr or "sparse checkout failed").strip()[:500]
            return make_row(repo, sha, steps, "error", err, [], started)
        workflow_root = root / ".github" / "workflows"
        workflow_files = sorted(path for path in workflow_root.glob("*") if path.is_file() and path.suffix.lower() in (".yml", ".yaml")) if workflow_root.exists() else []
        if not workflow_files:
            return make_row(repo, sha, steps, "no_workflows", None, [], started)
        steps.append("scan_workflows")
        findings: list[dict] = []
        for path in workflow_files:
            text = path.read_text(errors="replace")
            for match in USES_RE.finditer(text):
                value = match.group(1).rstrip("'")
                if value.startswith("./") or value.startswith("docker://") or "@" not in value:
                    continue
                action, ref = value.rsplit("@", 1)
                if FULL_SHA_RE.fullmatch(ref):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                excerpt = text.splitlines()[line - 1].strip()[:240]
                findings.append({"path": str(path.relative_to(root)), "line": line, "action": action, "ref": ref, "excerpt": excerpt})
        steps.append("classify_pins")
        return make_row(repo, sha, steps, "finding" if findings else "clean", None, findings, started)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def make_row(repo: dict, sha: str | None, steps: list[str], outcome: str, error: str | None, findings: list[dict], started: float) -> dict:
    return {
        "repo": repo["fullName"], "sha": sha, "steps": steps,
        "model": "deterministic-python-regex-v1", "tokens": 0,
        "cost_usd": 0.0, "seconds": round(time.monotonic() - started, 3),
        "outcome": outcome, "error": error, "findings": findings,
        "language": repo.get("language"), "size": repo.get("size"),
        "stars": repo.get("stargazersCount"), "stratum": repo.get("stratum"),
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def scan(limit: int | None, workers: int) -> None:
    repos = [json.loads(line) for line in REPOS.read_text().splitlines() if line.strip()]
    if limit is not None:
        repos = repos[:limit]
    done: dict[str, dict] = {}
    if RUNS.exists():
        for line in RUNS.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["repo"]] = row
    pending = [repo for repo in repos if repo["fullName"] not in done]
    with RUNS.open("a") as handle, concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check_repo, repo): repo for repo in pending}
        for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                row = future.result()
            except Exception as exc:
                row = make_row(futures[future], None, ["runner"], "error", f"{type(exc).__name__}: {exc}", [], time.monotonic())
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            if idx % 20 == 0 or idx == len(pending):
                print(f"completed {idx}/{len(pending)} pending; {row['outcome']}", flush=True)


def summarise() -> None:
    rows = [json.loads(line) for line in RUNS.read_text().splitlines() if line.strip()]
    frozen = [json.loads(line) for line in REPOS.read_text().splitlines() if line.strip()]
    outcomes = Counter(row["outcome"] for row in rows)
    findings = [row for row in rows if row["outcome"] == "finding"]
    failure_causes = Counter()
    for row in rows:
        if row["outcome"] != "error":
            continue
        error = row.get("error") or "unknown"
        if "git-lfs" in error:
            failure_causes["git_lfs_not_installed"] += 1
        elif "Repository not found" in error:
            failure_causes["repository_removed_after_freeze"] += 1
        elif "RPC failed" in error:
            failure_causes["git_transport_rpc"] += 1
        else:
            failure_causes["other"] += 1
    total_instances = sum(len(row["findings"]) for row in findings)
    seconds = sum(row["seconds"] for row in rows)
    summary = {
        "schema": "helicon-eval-at-scale-v1",
        "run_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "population": {
            "frozen_repositories": len(frozen),
            "frozen_sha256": hashlib.sha256(REPOS.read_bytes()).hexdigest(),
            "languages": dict(Counter(row["language"] for row in frozen)),
            "size_kb": {
                "min": min(row["size"] for row in frozen),
                "median": sorted(row["size"] for row in frozen)[len(frozen) // 2],
                "max": max(row["size"] for row in frozen),
            },
        },
        "execution": {
            "runs": len(rows), "unattended_runs": len(rows),
            "unattended_pct": round(100 * len(rows) / len(rows), 1) if rows else 0,
            "outcomes": dict(outcomes),
            "failure_rate": round(outcomes["error"] / len(rows), 4) if rows else None,
            "failure_causes_top_5": [{"cause": cause, "runs": count} for cause, count in failure_causes.most_common(5)],
            "wall_seconds_sum": round(seconds, 3),
            "median_seconds": sorted(row["seconds"] for row in rows)[len(rows) // 2] if rows else None,
        },
        "cost": {"model": "deterministic local check", "total_usd": 0.0, "per_run_usd": 0.0, "tokens": 0},
        "findings": {"repositories": len(findings), "instances": total_instances},
        "precision": None,
        "definition": "External GitHub Action uses-reference not pinned to a full 40-character commit SHA.",
        "limits": ["This measures reproducibility and action-reference mutability, not exploitability.", "Local actions and Docker images are excluded."],
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def label() -> None:
    rows = [json.loads(line) for line in RUNS.read_text().splitlines() if line.strip()]
    candidates = []
    for row in rows:
        for finding in row.get("findings", []):
            candidates.append({"repo": row["repo"], "sha": row["sha"], **finding})
    rng = random.Random(20261018)
    sample = rng.sample(candidates, min(50, len(candidates)))
    labels = []
    for finding in sample:
        value = f"{finding['action']}@{finding['ref']}"
        url = "https://raw.githubusercontent.com/{repo}/{sha}/{path}".format(
            repo=finding["repo"], sha=finding["sha"],
            path=urllib.parse.quote(finding["path"], safe="/"),
        )
        source_error = None
        matched_line = None
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "at-scale-read-only-eval/1"})
            with urllib.request.urlopen(request, timeout=30) as response:
                source = response.read().decode("utf-8", "replace")
            for line_number, source_line in enumerate(source.splitlines(), 1):
                if value in source_line and "uses" in source_line:
                    matched_line = {"line": line_number, "excerpt": source_line.strip()[:240]}
                    break
        except Exception as exc:
            source_error = f"{type(exc).__name__}: {exc}"
        external = not value.startswith("./") and not value.startswith("docker://")
        full_sha = bool(FULL_SHA_RE.fullmatch(finding["ref"]))
        label_value = external and not full_sha and matched_line is not None
        labels.append({
            **finding, "label": "true_positive" if label_value else "false_positive",
            "label_method": "fresh raw source at frozen SHA",
            "source_url": url, "source_match": matched_line, "source_error": source_error,
        })
    tp = sum(row["label"] == "true_positive" for row in labels)
    result = {"seed": 20261018, "population": "all detected unpinned action references", "sample_n": len(labels), "true_positives": tp, "false_positives": len(labels) - tp, "precision": round(tp / len(labels), 4) if labels else None, "labels": labels}
    LABELS.write_text(json.dumps(result, indent=2) + "\n")
    summary = json.loads(SUMMARY.read_text())
    summary["precision"] = {key: result[key] for key in ("population", "sample_n", "true_positives", "false_positives", "precision")}
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("sample_n", "true_positives", "false_positives", "precision")}, indent=2))


def retry_errors() -> None:
    rows = [json.loads(line) for line in RUNS.read_text().splitlines() if line.strip()]
    kept = [row for row in rows if row.get("outcome") != "error"]
    removed = len(rows) - len(kept)
    temp = RUNS.with_suffix(".jsonl.tmp")
    with temp.open("x") as handle:
        for row in kept:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    temp.replace(RUNS)
    print(json.dumps({"removed_error_rows": removed, "remaining_rows": len(kept)}))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("freeze")
    scan_parser = sub.add_parser("scan")
    scan_parser.add_argument("--limit", type=int)
    scan_parser.add_argument("--workers", type=int, default=8)
    sub.add_parser("summarise")
    sub.add_parser("label")
    sub.add_parser("retry-errors")
    args = parser.parse_args()
    if args.command == "freeze": freeze()
    elif args.command == "scan": scan(args.limit, args.workers)
    elif args.command == "summarise": summarise()
    elif args.command == "label": label()
    elif args.command == "retry-errors": retry_errors()


if __name__ == "__main__":
    main()
