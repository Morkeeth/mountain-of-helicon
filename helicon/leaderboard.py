"""helicon leaderboard - a population-scale, execution-free model reliability read.

`route` reads YOUR board (one model). This reads git history across many repos,
where multiple models/harnesses actually co-authored commits (public repos carry
'Co-authored-by: Cursor / Claude / Copilot' trailers). It ranks models by how
often their commits SURVIVE vs get REVERTED.

Honesty rules:
  - Outcome is git-only and execution-free: a commit later reverted (a revert
    commit says 'This reverts commit <sha>') is a real failure; everything else
    is 'survived'. NO test execution, so it is bounded and cannot freeze a
    machine (the whole reason this is separate from route --record --run).
  - 'survived' is a weaker signal than execution-verified, and it is labeled as
    such. The DISCRIMINATOR is the revert rate: low reverts = reliable. Ranking
    is Wilson lower bound on survival, so sample size is respected.
  - Model from the co-author trailer (canonical), harness from the signature.
    No trailer -> the commit is skipped, never attributed to a guessed author.
"""
import re

from helicon.route import canonical_model, harness_of
from helicon.review_terminals import _git

# conventional-commit prefix -> task class
_TYPE_RX = re.compile(r"^(\w+)(?:\([^)]*\))?!?:", re.I)
_TASK_OF_TYPE = {
    "feat": "feature", "fix": "bugfix", "test": "testing", "tests": "testing",
    "docs": "docs", "doc": "docs", "refactor": "refactor", "perf": "perf",
    "chore": "infra", "build": "infra", "ci": "infra", "style": "style",
}
_REVERTS_RX = re.compile(r"This reverts commit ([0-9a-f]{7,40})", re.I)
_US, _RS = "\x1f", "\x1e"        # unit + record separators for robust parsing


def task_of_subject(subject: str) -> str:
    m = _TYPE_RX.match(subject.strip())
    if m:
        return _TASK_OF_TYPE.get(m.group(1).lower(), "other")
    return "other"


def parse_commits(raw: str) -> list[dict]:
    """Parse the delimited `git log` blob into commit records. Kept pure (no git)
    so the parsing + attribution is unit-testable without a repo."""
    out = []
    for rec in raw.split(_RS):
        rec = rec.strip("\n")
        if not rec:
            continue
        parts = rec.split(_US)
        if len(parts) < 3:
            continue
        sha, subject, trailers = parts[0].strip(), parts[1], parts[2]
        coauthors = [l.strip() for l in trailers.splitlines() if l.strip()]
        # first agent trailer wins (a human co-author after it does not override)
        agent = next((c for c in coauthors
                      if harness_of(c) != "unknown"), coauthors[0] if coauthors else "")
        if not agent:
            continue                     # no attributable author -> skip, never guess
        out.append({"sha": sha, "subject": subject,
                    "model": canonical_model(agent), "harness": harness_of(agent),
                    "task_class": task_of_subject(subject)})
    return out


def scan_repo(repo: str, max_commits: int = 500) -> list[dict]:
    """One repo's recent commits, attributed, tagged survived/reverted."""
    fmt = f"%H{_US}%s{_US}%(trailers:key=Co-authored-by,valueonly){_RS}"
    raw = _git(repo, "log", f"--format={fmt}", f"-{max_commits}")
    commits = parse_commits(raw)
    reverted = set()
    for m in _REVERTS_RX.finditer(_git(repo, "log", "--format=%b", f"-{max_commits}")):
        reverted.add(m.group(1))
    # a full sha is reverted if any recorded (possibly short) sha prefixes it
    rev_prefixes = tuple(reverted)
    for c in commits:
        c["reverted"] = any(c["sha"].startswith(p) for p in rev_prefixes)
        c["repo"] = repo
    return commits


def aggregate_commits(commits: list[dict], by_task: bool = False) -> list[dict]:
    """Pure aggregation (no git): commits -> ranked per (model, harness[, task])
    rows, Wilson-scored on survival. Testable without a repo."""
    from helicon.route import wilson_lower
    agg: dict = {}
    for c in commits:
        key = (c["model"], c["harness"]) + ((c["task_class"],) if by_task else ())
        a = agg.setdefault(key, {"commits": 0, "reverted": 0})
        a["commits"] += 1
        a["reverted"] += 1 if c.get("reverted") else 0
    rows = []
    for key, a in agg.items():
        survived = a["commits"] - a["reverted"]
        rows.append({
            "model": key[0], "harness": key[1],
            "task_class": key[2] if by_task else None,
            "commits": a["commits"], "reverted": a["reverted"], "survived": survived,
            "revert_rate": round(a["reverted"] / a["commits"], 3) if a["commits"] else 0.0,
            "survival_lb": round(wilson_lower(survived, a["commits"]), 3),
        })
    rows.sort(key=lambda r: (r["survival_lb"], r["commits"]), reverse=True)
    return rows


def build_leaderboard(repos: list[str], max_commits: int = 500,
                      by_task: bool = False) -> dict:
    commits = []
    for repo in repos:
        commits.extend(scan_repo(repo, max_commits))
    rows = aggregate_commits(commits, by_task=by_task)
    return {"repos": len(repos), "commits": len(commits), "by_task": by_task, "rows": rows}


def format_leaderboard(lb: dict) -> str:
    rows = lb["rows"]
    if not rows:
        return ("\n  No attributable commits found (no agent co-author trailers in "
                "these repos).\n")
    out = ["", f"  MODEL RELIABILITY LEADERBOARD — {lb['commits']} attributed commit(s) "
           f"across {lb['repos']} repo(s)",
           "  (git-only: survived vs reverted; execution-free, revert = the failure signal)", ""]
    hdr = f"  {'model':14}  {'harness':12}  "
    if lb["by_task"]:
        hdr += f"{'task':10}  "
    hdr += f"{'commits':>7}  {'reverts':>7}  {'revert%':>7}  {'survival LB':>11}"
    out.append(hdr)
    for r in rows:
        line = f"  {r['model']:14}  {r['harness']:12}  "
        if lb["by_task"]:
            line += f"{(r['task_class'] or ''):10}  "
        line += (f"{r['commits']:>7}  {r['reverted']:>7}  "
                 f"{r['revert_rate']*100:>6.1f}%  {r['survival_lb']:>11}")
        out.append(line)
    if len({r["model"] for r in rows}) < 2:
        out.append("")
        out.append("  (one model here — point at repos with diverse agent trailers "
                   "for a real cross-model ranking)")
    out.append("")
    return "\n".join(out)
