"""helicon sweep — the doorway gate over MANY repos, not one.

The doorway answers one repo: does its loaded agent-context contain claims the
running code disproves? `sweep` runs that SAME verdict — `helicon.doorway.verdict`,
reused as-is, no second probe path — over a whole corpus: clone each repo shallow
into a temp dir, score it, keep the receipt, throw the clone away. Concurrent,
per-repo timeout, nothing written back to any clone.

Its point is reach. Pointed at the public repos that ship a CLAUDE.md /
AGENTS.md / .cursorrules, it measures a systemic question: what fraction advertise
a capability, a path, or a command their own code contradicts — each finding
carrying the command that proved it. A repo that cannot be scored (clone failed,
no agent-rules file, timeout) is reported as such, never counted as clean.
"""
import concurrent.futures
import os
import shutil
import subprocess
import tempfile
from collections import Counter

from helicon import doorway

# Repo-level outcomes. Only 'scored' repos enter the denominator; everything
# else is an honest exclusion, reported by reason.
SCORED = "scored"
CLONE_FAILED = "clone-failed"
NO_RULES = "no-rules-file"
TIMEOUT = "timeout"
ERROR = "error"


def classify_kind(probe: str | None) -> str:
    """The claim kind, read off the probe command that judged it — no second
    classification pass, just a label for the command already run."""
    p = (probe or "").lower()
    if "ls-files" in p or "test -f" in p:
        return "named-path-gone"
    if "grep" in p:
        return "retired-capability-advertised"
    if "log" in p:
        return "quoted-command-output-disagrees"
    if "eth_call" in p or "owner()" in p:
        return "chain-authority-mismatch"
    return "other"


def _clone(spec: str, dst: str, timeout: int) -> tuple[bool, str]:
    url = spec if spec.startswith(("http://", "https://", "git@")) \
        else f"https://github.com/{spec}"
    try:
        p = subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", url, dst],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except subprocess.TimeoutExpired:
        return False, "clone timed out"
    return (p.returncode == 0 and os.path.isdir(dst)), (p.stderr or "")[:200]


def _findings(contradicted: list[dict]) -> list[dict]:
    out = []
    for b in contradicted:
        out.append({
            "where": f"{b['file']}:{b['line']}" if b.get("line") else b.get("file"),
            "kind": classify_kind(b.get("probe")),
            "claim": (b.get("text") or "")[:200],
            "probe": b.get("probe"),
            "stdout": (b.get("output") or "").splitlines()[:4],
            "why": b.get("why"),
        })
    return out


def sweep_repo(spec: str, *, timeout: int = 90, config: dict | None = None) -> dict:
    """Score one repo. `spec` is 'owner/name', a clone URL, or a LOCAL directory
    (used directly, not cloned — this is how the tests stay hermetic)."""
    from helicon.db import init_db

    local = os.path.isdir(spec)
    tmp = tempfile.mkdtemp(prefix="helicon-sweep-")   # holds the temp DB (+ clone)
    repo_dir = spec
    try:
        if not local:
            repo_dir = os.path.join(tmp, "repo")
            ok, err = _clone(spec, repo_dir, timeout)
            if not ok:
                status = TIMEOUT if "timed out" in err else CLONE_FAILED
                return {"repo": spec, "status": status, "error": err,
                        "contradicted": 0, "findings": []}
        if not doorway._seed_docs(repo_dir):
            return {"repo": spec, "status": NO_RULES, "contradicted": 0, "findings": []}
        conn = init_db(os.path.join(tmp, "sweep.db"))
        try:
            v = doorway.verdict(conn, repo_dir, config)
        finally:
            conn.close()
        findings = _findings(v.get("contradicted") or [])
        return {"repo": spec, "status": SCORED,
                "contradicted": len(findings), "findings": findings}
    except Exception as e:  # noqa: BLE001 — one bad repo must not sink the sweep
        return {"repo": spec, "status": ERROR, "error": f"{type(e).__name__}: {e}",
                "contradicted": 0, "findings": []}
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def run_sweep(repos: list[str], *, jobs: int = 8, timeout: int = 90,
              config: dict | None = None) -> dict:
    """Score a corpus concurrently. Returns the aggregate + every per-repo result
    (findings included), so the report can cite command + stdout per finding."""
    repos = [r.strip() for r in repos if r and r.strip()]
    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        futs = [ex.submit(sweep_repo, r, timeout=timeout, config=config) for r in repos]
        for f in concurrent.futures.as_completed(futs):
            results.append(f.result())
    results.sort(key=lambda r: (-r["contradicted"], r["repo"]))

    scored = [r for r in results if r["status"] == SCORED]
    flagged = [r for r in scored if r["contradicted"] > 0]
    by_status = dict(Counter(r["status"] for r in results))
    by_kind = dict(Counter(f["kind"] for r in scored for f in r["findings"]))
    dist = dict(Counter(r["contradicted"] for r in scored))
    return {
        "n_input": len(repos),
        "scored": len(scored),
        "flagged": len(flagged),
        "rate": round(len(flagged) / len(scored), 4) if scored else None,
        "findings_total": sum(r["contradicted"] for r in scored),
        "by_status": by_status,
        "by_kind": by_kind,
        "distribution": {str(k): v for k, v in sorted(dist.items())},
        "results": results,
    }


def load_corpus(path: str) -> list[str]:
    """One repo spec per line ('owner/name' or a URL); '#' comments and blanks
    ignored. This is the reproducible corpus a stranger reruns."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            s = line.split("#", 1)[0].strip()
            if s:
                out.append(s)
    return out


def format_sweep(sc: dict, limit: int = 20) -> str:
    lines = ["", "  helicon sweep — the doorway gate over a corpus", ""]
    rate = "n/a" if sc["rate"] is None else f"{sc['rate'] * 100:.1f}%"
    lines.append(f"  {sc['scored']} repos scored · {sc['flagged']} contain a claim "
                 f"their code disproves ({rate})")
    lines.append(f"  {sc['findings_total']} contradictions total")
    excl = {k: v for k, v in sc["by_status"].items() if k != SCORED}
    if excl:
        lines.append("  excluded (not counted): "
                     + ", ".join(f"{v} {k}" for k, v in sorted(excl.items())))
    if sc["by_kind"]:
        lines.append("  by kind: "
                     + ", ".join(f"{v} {k}" for k, v in sorted(sc["by_kind"].items(),
                                                               key=lambda x: -x[1])))
    lines.append("")
    shown = 0
    for r in sc["results"]:
        if r["contradicted"] == 0:
            continue
        lines.append(f"  {r['repo']}  ({r['contradicted']} contradicted)")
        for f in r["findings"][:3]:
            lines.append(f"     [{f['kind']}] {f['where']}")
            lines.append(f'        claim  "{f["claim"]}"')
            if f.get("probe"):
                lines.append(f"        probe  $ {f['probe']}")
            for i, ln in enumerate(f.get("stdout") or []):
                lines.append(f"        {'stdout' if i == 0 else '      '} {ln}")
        shown += 1
        if shown >= limit:
            lines.append(f"  … and more (showing {limit} flagged repos)")
            break
    lines.append("")
    return "\n".join(lines)
