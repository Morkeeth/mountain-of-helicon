"""RUN THIS — one command reviews a repo's agent setup, on evidence, for a stranger.

    python3 -m helicon.review <repo>            # review that repo
    python3 -m helicon.review                    # review the current directory

No key, no LLM, no torch. It reads the repo's instruction files (CLAUDE.md / AGENTS.md /
.cursorrules / …) and answers the one question a coding agent can't ask for itself: does
this setup LIE to me? Two checks that work on a repo Helicon has never seen:

  1. POINTERS   — does the file point at files that exist?      (helicon.pointers)
  2. COMMANDS   — does it name commands the repo actually has?   (helicon.commands)

Each finding names the exact file:line and the contradicting repo fact — the evidence,
not a score. WHAT IT'S BASED ON is printed at the end: the ROT catalogue's instruction-
vs-repo classes, and the finding that stale context files measurably degrade agents.
"""
from __future__ import annotations

from helicon.pointers import check_pointers
from helicon.commands import check_commands

_BASIS = (
    "Based on: Helicon's ROT catalogue (instruction-vs-repo drift classes) · "
    "ETH Zurich ICSE 2026 — LLM-written context files cut task success 2-3% while "
    "raising cost >20% · arXiv 2511.12884 — 75.9% of agent context files carry test "
    "procedures that rot. Every finding above is verifiable at the named file:line."
)


def review(repo_root: str) -> dict:
    return {"pointers": check_pointers(repo_root), "commands": check_commands(repo_root)}


def format_review(repo_root: str, res: dict) -> str:
    p, c = res["pointers"], res["commands"]
    broken = p["broken"] + c["broken"]
    lines = [f"HELICON REVIEW — {repo_root}", ""]

    if p["verdict"] == "ROT FOUND":
        lines.append(f"✗ {p['broken']} instruction pointer(s) point at files not in the repo:")
        lines += [f"    {r['receipt']}" for r in p["receipts"]]
    elif p["verdict"] == "CLEAN":
        lines.append(f"✓ pointers: {p['checked']} file reference(s) all resolve")
    else:
        lines.append("· pointers: no instruction file with checkable references")

    if c["verdict"] == "ROT FOUND":
        lines.append(f"✗ {c['broken']} command(s) the repo does not have:")
        lines += [f"    {r['receipt']}" for r in c["receipts"]]
    elif c["verdict"] == "CLEAN":
        lines.append(f"✓ commands: {c['checked']} documented command(s) all exist")
    else:
        lines.append("· commands: no instruction file names a resolvable command")

    lines.append("")
    if broken:
        lines.append(f"VERDICT: {broken} way(s) this setup lies to its agent. Fix the lines above.")
    elif p["verdict"] == "UNMEASURED" and c["verdict"] == "UNMEASURED":
        lines.append("VERDICT: no instruction file found to review "
                     "(no CLAUDE.md / AGENTS.md / .cursorrules).")
    else:
        lines.append("VERDICT: this setup does not lie to its agent — every reference checks out.")
    lines += ["", _BASIS]
    return "\n".join(lines)


def main(argv=None) -> int:
    import os
    import sys
    args = argv if argv is not None else sys.argv[1:]
    repo = os.path.abspath(args[0]) if args else os.getcwd()
    res = review(repo)
    print(format_review(repo, res))
    broken = res["pointers"]["broken"] + res["commands"]["broken"]
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
