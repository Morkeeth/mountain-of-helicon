"""Version/framework claim vs manifest — "we use React 18 / Python 3.11" graded.

Slice 2 of the wedge (PRD-2026-08 §6). A context file constantly pins a stack: "we use
React 18", "Python 3.11", "Node 20", "TypeScript 5". These are executable claims in the
weak sense — a stranger's agent trusts them — and they rot the moment `package.json` says
19. Unlike execute.py this is DETERMINISTIC and runs nothing: the claimed MAJOR version is
compared against the version the manifest/lockfile actually pins. Zero false-positive risk,
zero execution.

Graded sources (only when one exists — else UNVERIFIABLE, never a false alarm):
  React/Vue/Next/Svelte/Angular/TypeScript/Express/Vite  -> package.json dep major
  Python <maj.min>                                       -> pyproject requires-python / .python-version
  Node <maj>                                             -> .nvmrc / package.json engines.node

Run standalone:  python3 -m helicon.versions <repo_root> [instruction_file ...]
"""
from __future__ import annotations

import json
import os
import re

from helicon.pointers import DEFAULT_INSTRUCTION_FILES, _NEGATION

UPHELD = "UPHELD"
CONTRADICTED = "CONTRADICTED"
UNVERIFIABLE = "UNVERIFIABLE"

# claim word -> package.json dependency key. Only well-known packages with an
# unambiguous manifest home are graded.
_JS_PKG = {
    "react": "react", "vue": "vue", "next": "next", "next.js": "next", "nextjs": "next",
    "svelte": "svelte", "angular": "@angular/core", "typescript": "typescript",
    "express": "express", "vite": "vite",
}
# "React 18", "Next.js 14", "TypeScript v5" — name then major.
_RE_JS = re.compile(
    r"\b(React|Vue|Next\.?js|Svelte|Angular|TypeScript|Express|Vite)\b\s*v?(\d{1,3})\b",
    re.I)
_RE_PY = re.compile(r"\bPython\s*v?(\d+\.\d+)\b", re.I)
_RE_NODE = re.compile(r"\bNode(?:\.js|JS)?\s*v?(\d{1,3})\b", re.I)


def _read(repo_root: str, rel: str) -> str | None:
    try:
        with open(os.path.join(repo_root, rel), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _pkg_json(repo_root: str) -> dict:
    raw = _read(repo_root, "package.json")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _dep_major(pkg: dict, name: str) -> int | None:
    """The pinned MAJOR of a dependency, or None if not present/unparseable."""
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        spec = (pkg.get(section) or {}).get(name)
        if isinstance(spec, str):
            m = re.search(r"(\d+)", spec)   # ^18.2.0 / >=19 / 18.x -> first int = major
            if m:
                return int(m.group(1))
    return None


def _python_requirement(repo_root: str) -> tuple[str, str] | None:
    """(source, raw_spec) the repo pins for Python, or None."""
    pv = _read(repo_root, ".python-version")
    if pv and pv.strip():
        return (".python-version", pv.strip().splitlines()[0].strip())
    pt = _read(repo_root, "pyproject.toml")
    if pt:
        m = re.search(r'requires-python\s*=\s*["\']([^"\']+)["\']', pt)
        if m:
            return ("pyproject.toml requires-python", m.group(1).strip())
    return None


def _node_requirement(repo_root: str) -> tuple[str, str] | None:
    nv = _read(repo_root, ".nvmrc")
    if nv and nv.strip():
        return (".nvmrc", nv.strip().splitlines()[0].strip())
    pkg = _pkg_json(repo_root)
    eng = (pkg.get("engines") or {}).get("node")
    if isinstance(eng, str) and eng.strip():
        return ("package.json engines.node", eng.strip())
    return None


def _grade_js(pkg: dict, name: str, claimed: int) -> tuple[str, str]:
    # name is a captured token like "React" / "Next.js" / "Nextjs" — all are _JS_PKG keys.
    key = _JS_PKG.get(name.lower(), _JS_PKG.get(name.lower().replace(".", ""), name.lower()))
    major = _dep_major(pkg, key)
    if major is None:
        return UNVERIFIABLE, f"no '{key}' in package.json to compare"
    if major == claimed:
        return UPHELD, f"package.json pins {key} {major} (claim {claimed} holds)"
    return CONTRADICTED, f"doc says {name} {claimed}, package.json pins {key} {major}"


def _grade_python(repo_root: str, claimed: str) -> tuple[str, str]:
    req = _python_requirement(repo_root)
    if req is None:
        return UNVERIFIABLE, "no pyproject requires-python or .python-version to compare"
    src, spec = req
    nums = re.findall(r"\d+", spec)
    cmaj, cmin = claimed.split(".")
    # .python-version usually pins exactly (3.11.x); requires-python is a range (>=3.11).
    if src == ".python-version" and len(nums) >= 2:
        if (nums[0], nums[1]) == (cmaj, cmin):
            return UPHELD, f"{src} pins {spec} (claim {claimed} holds)"
        return CONTRADICTED, f"doc says Python {claimed}, {src} pins {spec}"
    # range form: a lower bound whose maj.min differs from the claim is a contradiction.
    m = re.search(r"(\d+)\.(\d+)", spec)
    if m:
        if (m.group(1), m.group(2)) == (cmaj, cmin):
            return UPHELD, f"{src} is {spec} (claim {claimed} consistent)"
        return CONTRADICTED, f"doc says Python {claimed}, {src} is {spec}"
    return UNVERIFIABLE, f"{src} {spec!r} has no comparable maj.min"


def _grade_node(repo_root: str, claimed: int) -> tuple[str, str]:
    req = _node_requirement(repo_root)
    if req is None:
        return UNVERIFIABLE, "no .nvmrc or package.json engines.node to compare"
    src, spec = req
    m = re.search(r"(\d+)", spec)
    if not m:
        return UNVERIFIABLE, f"{src} {spec!r} has no comparable major"
    if int(m.group(1)) == claimed:
        return UPHELD, f"{src} pins {spec} (claim {claimed} holds)"
    return CONTRADICTED, f"doc says Node {claimed}, {src} pins {spec}"


def check_versions(repo_root: str, files: list[str] | None = None) -> dict:
    """Grade every framework/runtime version claim in the instruction files against the
    manifests. rot.py-shaped dict; per-claim verdict on each receipt. Deterministic."""
    targets = [f for f in (files or DEFAULT_INSTRUCTION_FILES)
               if os.path.exists(os.path.join(repo_root, f))]
    pkg = _pkg_json(repo_root)

    receipts: list[dict] = []
    read_files: list[str] = []
    seen: set[tuple] = set()

    def add(rel, i, line, name, claimed_disp, verdict, why):
        key = (name.lower(), str(claimed_disp))
        if key in seen:
            return
        # a negated mention ("we no longer use React 17") is not a live claim.
        if _NEGATION.search(line):
            return
        seen.add(key)
        receipts.append({"kind": "version", "raw": f"{name} {claimed_disp}",
                         "file": rel, "line_no": i, "verdict": verdict,
                         "receipt": f"{rel}:{i} — {why}"})

    for rel in targets:
        text = _read(repo_root, rel)
        if text is None:
            continue
        read_files.append(rel)
        for i, line in enumerate(text.splitlines(), 1):
            for m in _RE_JS.finditer(line):
                name, maj = m.group(1), int(m.group(2))
                v, why = _grade_js(pkg, name, maj)
                add(rel, i, line, name, maj, v, why)
            for m in _RE_PY.finditer(line):
                v, why = _grade_python(repo_root, m.group(1))
                add(rel, i, line, "Python", m.group(1), v, why)
            for m in _RE_NODE.finditer(line):
                maj = int(m.group(1))
                v, why = _grade_node(repo_root, maj)
                add(rel, i, line, "Node", maj, v, why)

    graded = [r for r in receipts if r["verdict"] in (UPHELD, CONTRADICTED)]
    contradicted = [r for r in receipts if r["verdict"] == CONTRADICTED]
    if not graded:
        verdict = "UNMEASURED"
    else:
        verdict = "ROT FOUND" if contradicted else "CLEAN"
    return {"rid": "R16", "name": "Version/framework claim vs manifest",
            "verdict": verdict, "checked": len(graded), "broken": len(contradicted),
            "files": read_files, "receipts": receipts}


def format_versions(res: dict) -> str:
    head = f"[{res['rid']}] {res['name']}: {res['verdict']}"
    if res["verdict"] == "UNMEASURED":
        return head + "  (no version claim with a manifest to grade against)"
    head += f"  ({res['checked']} checked, {res['broken']} contradicted)"
    lines = [head]
    marks = {"UPHELD": "✓", "CONTRADICTED": "✗", "UNVERIFIABLE": "·"}
    for r in res["receipts"]:
        lines.append(f"  {marks[r['verdict']]} {r['verdict']} {r['receipt']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    import sys
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python3 -m helicon.versions <repo_root> [instruction_file ...]")
        return 2
    res = check_versions(args[0], args[1:] or None)
    print(format_versions(res))
    return 1 if res["verdict"] == "ROT FOUND" else 0


if __name__ == "__main__":
    raise SystemExit(main())
