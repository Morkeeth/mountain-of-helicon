"""RUN THIS — one command reviews a repo's agent setup, on evidence, for a stranger.

    python3 -m helicon.review <repo>            # review that repo
    python3 -m helicon.review                    # review the current directory

No key, no LLM, no torch. It reads the repo's instruction files (CLAUDE.md / AGENTS.md /
.cursorrules / …) and answers the one question a coding agent can't ask for itself: does
this setup LIE to me? Three checks that work on a repo Helicon has never seen:

  1. POINTERS   — does the file point at files that exist?      (helicon.pointers)
  2. COMMANDS   — does it name commands the repo actually has?   (helicon.commands)
  3. EXECUTION  — when the file claims a command PASSES, does it? (helicon.execute)

(1) and (2) are the existence tier — commoditized (ctxlint, agents-lint). (3) is the
wedge: it RUNS the documented test/build command and grades the claim against the real
exit code. It is OFF by default (running a stranger's code is opt-in) — set
HELICON_EXECUTE=1 to turn it on. Only allowlisted test/build/lint verbs ever run.

Each finding names the exact file:line and the contradicting repo fact — the evidence,
not a score. WHAT IT'S BASED ON is printed at the end: the ROT catalogue's instruction-
vs-repo classes, and the finding that stale context files measurably degrade agents.
"""
from __future__ import annotations

from helicon.pointers import check_pointers
from helicon.commands import check_commands
from helicon.execute import check_execution

_BASIS = (
    "Based on: Helicon's ROT catalogue (instruction-vs-repo drift classes) · "
    "ETH Zurich ICSE 2026 — LLM-written context files cut task success 2-3% while "
    "raising cost >20% · arXiv 2511.12884 — 75.9% of agent context files include test "
    "procedures, the executable claim that rots silently. Every finding above is "
    "verifiable at the named file:line."
)


import os as _os
import sys as _sys


def review(repo_root: str, execute: bool | None = None) -> dict:
    """Existence tier (pointers, commands) always; execute-and-compare opt-in.

    Executing a stranger's documented test/build command runs their code, so it is
    OFF by default. Pass execute=True, or set HELICON_EXECUTE=1, to turn it on (only
    allowlisted test/build/lint verbs ever run — see helicon.execute)."""
    if execute is None:
        execute = _os.environ.get("HELICON_EXECUTE", "").strip() not in ("", "0", "false")
    return {
        "pointers": check_pointers(repo_root),
        "commands": check_commands(repo_root),
        "execution": check_execution(repo_root, execute=execute),
    }

_ANSI = {"red": "31", "grn": "32", "ylw": "33", "dim": "2", "b": "1", "cyan": "36"}


def _color_on() -> bool:
    return _sys.stdout.isatty() and not _os.environ.get("NO_COLOR")


def _p(text: str, *styles: str) -> str:
    if not _color_on() or not styles:
        return text
    codes = ";".join(_ANSI[s] for s in styles if s in _ANSI)
    return f"\033[{codes}m{text}\033[0m"


def _grade(broken: int, checked: int) -> tuple[str, str]:
    if checked == 0:
        return "–", "dim"
    ratio = broken / checked
    if broken == 0:
        return "A", "grn"
    if ratio <= 0.15:
        return "B", "ylw"
    if ratio <= 0.4:
        return "C", "ylw"
    return "D" if ratio <= 0.7 else "F", "red"


def format_review(repo_root: str, res: dict) -> str:
    p, c = res["pointers"], res["commands"]
    e = res.get("execution", {"broken": 0, "checked": 0, "receipts": [], "executed": False})
    # A CONTRADICTED test — "the doc says this passes, it fails" — is a lie in exactly
    # the sense the headline means, so it counts. UNVERIFIABLE claims (not run) do not.
    broken = p["broken"] + c["broken"] + e.get("broken", 0)
    checked = p["checked"] + c["checked"] + e.get("checked", 0)
    name = _os.path.basename(repo_root.rstrip("/")) or repo_root
    L = [""]
    L.append("  " + _p("❄ HELICON", "b", "cyan") + _p(f"  reviewing {name}", "dim"))
    L.append("")

    # headline — the pitch line, worst case first.
    if broken:
        L.append("  " + _p(f"✗ Your setup lies to its agent in {broken} place"
                           f"{'' if broken == 1 else 's'}.", "b", "red"))
    elif checked:
        L.append("  " + _p("✓ This setup tells its agent the truth.", "b", "grn"))
    else:
        L.append("  " + _p("· No instruction file to review "
                           "(no CLAUDE.md / AGENTS.md / .cursorrules).", "dim"))
    L.append("")

    # ranked findings — broken first, each a clean one-liner.
    def rows(res_block, verb):
        for r in res_block["receipts"]:
            where, _, fact = r["receipt"].partition(" — ")
            # fact reads "<kind desc>: <thing>" — show just the <thing> + "not here".
            thing = fact.rsplit(": ", 1)[-1].strip() if ": " in fact else fact.strip()
            L.append("    " + _p("✗", "red") + " " + _p(where.strip(), "dim")
                     + "  " + _p(f"{verb} ", "b") + _p(thing, "b", "red")
                     + _p("  — not in this repo", "dim"))

    if p["broken"]:
        rows(p, "points at")
    if c["broken"]:
        rows(c, "runs")
    if broken:
        L.append("")

    # THIRD BLOCK — commands RAN vs their claim. The wedge: existence checks prove a
    # command is DEFINED; this proves the doc's claim that it PASSES is still true.
    ex_receipts = e.get("receipts", [])
    if ex_receipts:
        L.append("  " + _p("commands RAN vs their claim", "b")
                 + _p("   (execute-and-compare)", "dim"))
        if not e.get("executed"):
            n = len(ex_receipts)
            L.append("    " + _p("·", "ylw") + " "
                     + _p(f"{n} documented success claim{'' if n == 1 else 's'} found, "
                          "not run", "ylw")
                     + _p("  — set HELICON_EXECUTE=1 to verify", "dim"))
        else:
            marks = {"UPHELD": ("✓", "grn"), "CONTRADICTED": ("✗", "red"),
                     "UNVERIFIABLE": ("·", "dim")}
            for r in ex_receipts:
                sym, col = marks.get(r["verdict"], ("·", "dim"))
                where = f"{r['file']}:{r['line_no']}"
                if r["verdict"] == "CONTRADICTED":
                    L.append("    " + _p(sym, col) + " " + _p(where, "dim") + "  "
                             + _p("runs ", "b") + _p(f"`{r['raw']}`", "b", col)
                             + _p(f"  — claims it passes, real exit {r['exit']}", "dim"))
                    tail = (r.get("output") or "").strip().splitlines()[-3:]
                    for t in tail:
                        L.append("        " + _p(t[:100], "dim"))
                elif r["verdict"] == "UPHELD":
                    L.append("    " + _p(sym, col) + " " + _p(where, "dim") + "  "
                             + _p("runs ", "b") + _p(f"`{r['raw']}`", "b", col)
                             + _p("  — claim holds, exit 0", "dim"))
                else:
                    L.append("    " + _p(sym, col) + " " + _p(where, "dim") + "  "
                             + _p(f"`{r['raw']}`", "dim")
                             + _p(f"  — {r['receipt'].split(' — ', 1)[-1]}", "dim"))
        L.append("")

    # the grade + the narrative punch.
    if checked:
        g, gc = _grade(broken, checked)
        L.append("  " + _p(f"GRADE {g}", "b", gc)
                 + _p(f"   ·   {checked} reference{'' if checked == 1 else 's'} checked, "
                      f"{broken} broken", "dim"))
        if broken:
            L.append("  " + _p(f"An agent that trusts this file walks into {broken} dead "
                               f"end{'' if broken == 1 else 's'}.", "dim"))
        else:
            L.append("  " + _p("Every path and command an agent is told to use is real.", "dim"))
    L += ["", "  " + _p(_BASIS, "dim"), ""]
    return "\n".join(L)


def main(argv=None) -> int:
    import os
    import sys
    args = argv if argv is not None else sys.argv[1:]
    repo = os.path.abspath(args[0]) if args else os.getcwd()
    res = review(repo)
    print(format_review(repo, res))
    broken = (res["pointers"]["broken"] + res["commands"]["broken"]
              + res["execution"]["broken"])
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
