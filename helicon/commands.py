"""Command check: does an instruction file tell the agent to run commands the repo has?

The second repo-agnostic instruction-vs-repo class, after R13 pointers. An instruction
file constantly says "run `npm run build`", "`make test`", "`python3 scripts/seed.py`" —
and when a script is renamed or removed, the file sends the agent down a dead end that
looks authoritative. Like pointers, this is checkable on a repo Helicon has never seen:
the command either resolves to something the repo defines, or it does not.

Only the DETERMINISTICALLY resolvable command shapes are graded, so a miss is a real miss:
  npm run X / yarn X / pnpm X   -> X must be a key in package.json "scripts"
  make X                        -> X: must be a target in a Makefile
  ./path or bash path.sh        -> the script file must exist
  python[3] path.py / -m pkg    -> the file (or package dir) must exist in the repo
A bare `helicon scan`, `docker up`, `npx create-foo` etc. is NOT graded — its provider is
outside the repo, so absence proves nothing. UNMEASURED, never a false alarm.

Run standalone:  python3 -m helicon.commands <repo_root> [instruction_file ...]
"""
from __future__ import annotations

import json
import os
import re

from helicon.pointers import DEFAULT_INSTRUCTION_FILES, _NEGATION

# Command references inside inline code spans. Each group 1 = the token we resolve.
_RE_NPM = re.compile(r"`(?:npm run|yarn|pnpm(?: run)?)\s+([\w:.-]+)`")
_RE_MAKE = re.compile(r"`make\s+([\w.-]+)`")
_RE_PY = re.compile(r"`python3?\s+(?:-m\s+([\w.]+)|([\w./-]+\.py))[^`]*`")
_RE_SCRIPT = re.compile(r"`(?:bash|sh|\./)\s*([\w./-]+\.(?:sh|bash|py|js|ts))`")


def _pkg_scripts(repo_root: str) -> set[str]:
    p = os.path.join(repo_root, "package.json")
    try:
        with open(p, encoding="utf-8") as fh:
            return set(json.load(fh).get("scripts", {}) or {})
    except Exception:
        return set()


def _make_targets(repo_root: str) -> set[str]:
    out: set[str] = set()
    for name in ("Makefile", "makefile", "GNUmakefile"):
        p = os.path.join(repo_root, name)
        try:
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    m = re.match(r"^([A-Za-z0-9_.-]+)\s*:(?!=)", line)
                    if m:
                        out.add(m.group(1))
        except Exception:
            continue
    return out


def _file_in_repo(repo_root: str, rel: str) -> bool:
    rel = rel.strip().lstrip("./")
    if not rel:
        return False
    return os.path.exists(os.path.normpath(os.path.join(repo_root, rel)))


def _module_in_repo(repo_root: str, mod: str) -> bool:
    # a.b.c -> a/b/c.py or a/b/c/__init__.py
    parts = mod.split(".")
    base = os.path.join(repo_root, *parts)
    return os.path.exists(base + ".py") or os.path.isdir(base)


def check_commands(repo_root: str, files: list[str] | None = None) -> dict:
    targets = [f for f in (files or DEFAULT_INSTRUCTION_FILES)
               if os.path.exists(os.path.join(repo_root, f))]
    scripts = _pkg_scripts(repo_root)
    targets_mk = _make_targets(repo_root)

    checked: list[dict] = []
    read_files: list[str] = []
    for rel in targets:
        try:
            with open(os.path.join(repo_root, rel), encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        read_files.append(rel)
        for i, line in enumerate(lines, 1):
            for m in _RE_NPM.finditer(line):
                _grade(checked, "npm", m.group(1), m.group(1) in scripts, rel, i, line,
                       f"no '{m.group(1)}' in package.json scripts")
            for m in _RE_MAKE.finditer(line):
                _grade(checked, "make", m.group(1), m.group(1) in targets_mk, rel, i, line,
                       f"no '{m.group(1)}' target in Makefile")
            for m in _RE_PY.finditer(line):
                mod, path = m.group(1), m.group(2)
                if mod:
                    _grade(checked, "python-m", mod, _module_in_repo(repo_root, mod), rel, i, line,
                           f"module '{mod}' not in repo")
                elif path:
                    _grade(checked, "python", path, _file_in_repo(repo_root, path), rel, i, line,
                           f"script '{path}' not in repo")
            for m in _RE_SCRIPT.finditer(line):
                _grade(checked, "script", m.group(1), _file_in_repo(repo_root, m.group(1)),
                       rel, i, line, f"script '{m.group(1)}' not in repo")

    broken = [c for c in checked if not c["resolved"]]
    if not read_files or not checked:
        verdict = "UNMEASURED"
    else:
        verdict = "ROT FOUND" if broken else "CLEAN"
    return {"rid": "R14", "name": "Instruction commands vs repo", "verdict": verdict,
            "checked": len(checked), "broken": len(broken), "files": read_files,
            "receipts": [{"kind": c["kind"], "raw": c["raw"],
                          "receipt": f"{c['file']}:{c['line_no']} — {c['why']}"}
                         for c in broken]}


def _grade(acc, kind, raw, resolved, rel, line_no, line, why):
    # a described absence ("we removed `make old`") is not a broken command reference.
    if not resolved:
        prose = line.replace(raw, " ")
        if _NEGATION.search(prose):
            return
    if any(c["kind"] == kind and c["raw"] == raw for c in acc):
        return
    acc.append({"kind": kind, "raw": raw, "resolved": resolved,
                "file": rel, "line_no": line_no, "why": why})


def format_commands(res: dict) -> str:
    head = f"[{res['rid']}] {res['name']}: {res['verdict']}"
    if res["verdict"] == "UNMEASURED":
        return head + "  (no instruction file names a resolvable command)"
    head += f"  ({res['checked']} checked, {res['broken']} broken)"
    return "\n".join([head] + [f"  ✗ {r['kind']} {r['raw']}  →  {r['receipt']}"
                              for r in res["receipts"]])


def main(argv=None) -> int:
    import sys
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python3 -m helicon.commands <repo_root> [instruction_file ...]")
        return 2
    res = check_commands(args[0], args[1:] or None)
    print(format_commands(res))
    return 1 if res["verdict"] == "ROT FOUND" else 0


if __name__ == "__main__":
    raise SystemExit(main())
