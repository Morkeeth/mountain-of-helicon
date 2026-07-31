"""HELICON-BENCH — memory scored against commands that execute.

The open gap: LOCOMO, LongMemEval, STALE and PersistBench all score an agent's
memory against the user's own conversation — text vs text. None execute anything.
So a memory that is internally consistent but WRONG about the running system
passes every one of them. That is the exact failure Helicon's R13 probes catch:
a claim in CLAUDE.md that the code disproves.

HELICON-BENCH is that eval, made public and reproducible. Over a shipped corpus
of small repos (`bench/repos/`), it runs the real probes and scores each repo's
instruction docs by executed verdict:

  CONTRADICTED  a probe ran and the running code disagrees — stdout is the receipt
  UPHELD        a probe ran and the code agrees
  UNVERIFIABLE  no probe could run (no RPC, elided address, unprobeable claim)

Reproducible by construction: the corpus and the probes ship in this repo, and
every repo is staged into a throwaway git checkout at run time so all probe kinds
(kill-switch, path, command, chain) run identically on any machine. Anyone can
rerun it with `helicon bench` and get the same verdicts — because the verdicts
come from commands, not from a label we wrote down.
"""
import os
import shutil
import subprocess
import tempfile

from helicon import probes

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CORPUS = os.path.join(_REPO_ROOT, "bench", "repos")


def _stage(src: str) -> str:
    """Copy a shipped corpus repo into a temp git checkout so every probe kind
    runs at full fidelity (the corpus ships without nested .git dirs)."""
    tmp = tempfile.mkdtemp(prefix="helicon-bench-")
    dst = os.path.join(tmp, os.path.basename(src.rstrip("/")))
    shutil.copytree(src, dst)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    for cmd in (["git", "init", "-q"],
                ["git", "add", "-A"],
                ["git", "-c", "user.email=bench@helicon", "-c", "user.name=bench",
                 "commit", "-qm", "bench corpus"]):
        subprocess.run(cmd, cwd=dst, capture_output=True, env=env)
    return dst


def bench_repo(repo_path: str, config: dict | None = None,
               allow_network: bool = False) -> dict:
    """Score one repo: run every probe over its instruction docs, tally verdicts,
    and keep the receipt (command + stdout) for each contradicted claim."""
    staged = _stage(repo_path)
    try:
        results = probes.probe_docs(None, staged, config, allow_network)
    finally:
        shutil.rmtree(os.path.dirname(staged), ignore_errors=True)

    counts = {probes.CONTRADICTED: 0, probes.UPHELD: 0, probes.UNVERIFIABLE: 0}
    receipts = []
    for r in results:
        v = r.get("verdict")
        if v in counts:
            counts[v] += 1
        if v == probes.CONTRADICTED:
            receipts.append({
                "where": f"{r['file']}:{r['line']}" if r.get("line") else r["file"],
                "kind": r.get("kind"),
                "claim": (r.get("sentence") or "")[:180],
                "probe": r.get("probe"),
                "stdout": (r.get("output") or "").splitlines()[:4],
                "why": r.get("why"),
            })
    return {
        "repo": os.path.basename(repo_path.rstrip("/")),
        "probes": len(results),
        "contradicted": counts[probes.CONTRADICTED],
        "upheld": counts[probes.UPHELD],
        "unverifiable": counts[probes.UNVERIFIABLE],
        "receipts": receipts,
    }


def run_bench(corpus_dir: str | None = None, config: dict | None = None,
              allow_network: bool = False) -> dict:
    """Run HELICON-BENCH over every repo in the corpus. Deterministic: the same
    corpus + the same probes yield the same verdicts anywhere."""
    corpus_dir = corpus_dir or DEFAULT_CORPUS
    if not os.path.isdir(corpus_dir):
        return {"corpus": corpus_dir, "exists": False, "repos": [], "repo_count": 0}
    names = sorted(d for d in os.listdir(corpus_dir)
                   if os.path.isdir(os.path.join(corpus_dir, d)) and not d.startswith("."))
    repos = [bench_repo(os.path.join(corpus_dir, n), config, allow_network) for n in names]
    totals = {
        "probes": sum(r["probes"] for r in repos),
        "contradicted": sum(r["contradicted"] for r in repos),
        "upheld": sum(r["upheld"] for r in repos),
        "unverifiable": sum(r["unverifiable"] for r in repos),
    }
    return {"corpus": corpus_dir, "exists": True, "repos": repos,
            "repo_count": len(repos), "totals": totals, "executed": True}


def format_bench(sc: dict) -> str:
    if not sc.get("exists"):
        return f"\n  No bench corpus at {sc.get('corpus')}.\n"
    t = sc["totals"]
    lines = ["", "  HELICON-BENCH — memory scored against commands that execute", "",
             f"  {sc['repo_count']} repos · {t['probes']} probes executed",
             f"  {t['contradicted']} contradicted · {t['unverifiable']} unverifiable · "
             f"{t['upheld']} upheld", ""]
    lines.append(f"  {'repo':<20} {'probes':>6} {'contra':>7} {'unver':>6} {'upheld':>7}")
    for r in sc["repos"]:
        lines.append(f"  {r['repo'][:20]:<20} {r['probes']:>6} {r['contradicted']:>7} "
                     f"{r['unverifiable']:>6} {r['upheld']:>7}")
    lines.append("")
    for r in sc["repos"]:
        for rec in r["receipts"]:
            lines.append(f"  CONTRADICTED  {r['repo']}  {rec['where']}  [{rec['kind']}]")
            lines.append(f'     claim   "{rec["claim"]}"')
            if rec.get("probe"):
                lines.append(f"     probe   $ {rec['probe']}")
            for i, ln in enumerate(rec.get("stdout") or []):
                lines.append(f"     {'stdout ' if i == 0 else '       '} {ln}")
            lines.append("")
    lines.append("  Reproduce: helicon bench   (corpus + probes ship in bench/repos)")
    return "\n".join(lines)
