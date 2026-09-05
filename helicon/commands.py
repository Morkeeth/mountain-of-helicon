"""Command check: does an instruction file tell the agent to run commands the repo has?

The second repo-agnostic instruction-vs-repo class, after R13 pointers. An instruction
file constantly says "run `npm run build`", "`make test`", "`python3 scripts/seed.py`" —
and when a script is renamed or removed, the file sends the agent down a dead end that
looks authoritative. Like pointers, this is checkable on a repo Helicon has never seen:
the command either resolves to something the repo defines, or it does not.

Only the DETERMINISTICALLY resolvable command shapes are graded, so a miss is a real miss:
  npm run X / yarn X / pnpm X   -> X must be a key in package.json "scripts"
  cd DIR && npm run X           -> X must be in DIR/package.json scripts
  npm test|start|stop|restart   -> same as npm run <lifecycle>
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

# Command references inside inline code spans.
# npm lifecycle aliases (test/start/stop/restart) are scripts too — `npm test` ≡ `npm run test`.
# `cd web && npm run build` resolves against web/package.json.
# Do NOT grade `npm ci` / `npm install` / `npm publish` (external / non-script).
_RE_NPM = re.compile(
    r"`(?:cd\s+([\w./-]+)\s*&&\s*)?(?:npm run|yarn|pnpm(?: run)?)\s+([\w:.-]+)`"
    r"|`npm\s+(test|start|stop|restart)`"
)
_RE_MAKE = re.compile(r"`make\s+([\w.-]+)`")
_RE_PY = re.compile(r"`python3?\s+(?:-m\s+([\w.]+)|([\w./-]+\.py))[^`]*`")
_RE_SCRIPT = re.compile(r"`(?:bash|sh|\./)\s*([\w./-]+\.(?:sh|bash|py|js|ts))`")

# Clause breaks for described-absence: negation in a *different* clause must not
# silence a later imperative ("missing web/dist; run `npm run build`").
_CLAUSE_BREAK = re.compile(r"[.;](?:\s|$)|(?:\s[-–—]\s)")


def _clause_containing(line: str, idx: int) -> str:
    bounds = [0]
    for m in _CLAUSE_BREAK.finditer(line):
        bounds.append(m.end())
    bounds.append(len(line))
    for a, b in zip(bounds, bounds[1:]):
        if a <= idx < b:
            return line[a:b]
    return line


def _pkg_scripts(repo_root: str, subdir: str | None = None) -> set[str]:
    base = os.path.join(repo_root, subdir) if subdir else repo_root
    p = os.path.join(base, "package.json")
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
    scripts_cache: dict[str | None, set[str]] = {None: _pkg_scripts(repo_root)}
    targets_mk = _make_targets(repo_root)

    def scripts_for(subdir: str | None) -> set[str]:
        if subdir not in scripts_cache:
            scripts_cache[subdir] = _pkg_scripts(repo_root, subdir)
        return scripts_cache[subdir]

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
                # groups: (cd_dir?, script) | (None, None, lifecycle)
                script = m.group(2) or m.group(3)
                cd_dir = m.group(1)
                pkg = scripts_for(cd_dir)
                where = f"{cd_dir}/package.json" if cd_dir else "package.json"
                _grade(checked, "npm", script, script in pkg, rel, i, line,
                       f"no '{script}' in {where} scripts", match_start=m.start())
            for m in _RE_MAKE.finditer(line):
                _grade(checked, "make", m.group(1), m.group(1) in targets_mk, rel, i, line,
                       f"no '{m.group(1)}' target in Makefile", match_start=m.start())
            for m in _RE_PY.finditer(line):
                mod, path = m.group(1), m.group(2)
                if mod:
                    _grade(checked, "python-m", mod, _module_in_repo(repo_root, mod), rel, i, line,
                           f"module '{mod}' not in repo", match_start=m.start())
                elif path:
                    _grade(checked, "python", path, _file_in_repo(repo_root, path), rel, i, line,
                           f"script '{path}' not in repo", match_start=m.start())
            for m in _RE_SCRIPT.finditer(line):
                _grade(checked, "script", m.group(1), _file_in_repo(repo_root, m.group(1)),
                       rel, i, line, f"script '{m.group(1)}' not in repo", match_start=m.start())

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


def _grade(acc, kind, raw, resolved, rel, line_no, line, why, match_start: int = 0):
    # a described absence ("we removed `make old`") is not a broken command reference.
    # Negation must sit in the *same clause* as the command — otherwise
    # "missing web/dist; run `npm run build`" falsely silences a dead script.
    if not resolved:
        clause = _clause_containing(line, match_start)
        prose = clause.replace(raw, " ", 1)
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
