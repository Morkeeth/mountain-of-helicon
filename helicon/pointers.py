"""Pointer check: does an instruction file point at things the repo actually has?

THE GAP THIS CLOSES. docdrift.py catches count/list/eval drift, but only in
Helicon's OWN docs — it compares prose numbers to counts computed from Helicon's
package source, so it returns UNMEASURED on a repo it has never seen (rot.py R2/R13).
The lie-detector detected lies only in its author's repo.

A POINTER is repo-agnostic. "This file says to read `docs/SETUP.md`" is checkable
against ANY repo: the path either resolves or it does not, and a CLAUDE.md that sends
an agent to a file that is not there is lying to the agent no matter whose repo it is.
That is the one class of instruction-vs-repo drift that needs no knowledge of the
project, so it is the front door to grading a stranger's setup.

Competitor note (2026): `agents-lint` (github.com/giacomo/agents-lint) already flags
dead paths in AGENTS.md/CLAUDE.md. This matches that floor deterministically and is
built to feed Helicon's deeper doc-vs-live checks, which agents-lint does not do.

Five pointer shapes are extracted and graded, each against the live repo tree:
  IMPORT    `@path/to/file`            — Claude Code @import (Anthropic docs)
  MDLINK    `[label](./path)`          — a markdown link to a LOCAL path (not a URL)
  WIKILINK  `[[Note Name]]`            — an Obsidian/wiki link resolved by basename
  BACKTICK  `` `path/with/slash.ext` `` — a path-shaped token in code font
  BARE      `path/with/slash.ext`      — a path-shaped token in prose

Every candidate must LOOK like an intra-repo path (contain a slash or a known code
extension, no scheme, no leading http). URLs, anchors, and prose are excluded up front
so the false-positive rate stays low — a broken pointer must be a real broken pointer.

Run standalone:  python3 -m helicon.pointers <repo_root> [instruction_file ...]
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

# Files that are, by convention, instructions to an agent. Checked when no explicit
# file list is given.
DEFAULT_INSTRUCTION_FILES = (
    "CLAUDE.md", "AGENTS.md", ".cursorrules", "AGENT.md", "CONTEXT.md",
    ".github/copilot-instructions.md", "GEMINI.md",
)

# A token is path-shaped if it carries a slash or ends in a code-ish extension. This is
# what keeps prose ("the auth module") from being graded as a pointer.
_CODE_EXT = (
    ".md", ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml", ".toml",
    ".sh", ".rs", ".go", ".java", ".rb", ".txt", ".cfg", ".ini", ".env", ".sql",
    ".html", ".css", ".ipynb", ".lock", ".mjs", ".cjs",
)
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)

# Extraction patterns.
_RE_IMPORT = re.compile(r"(?<![`\w])@([\w./-]+)")
_RE_MDLINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_RE_WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
_RE_BACKTICK = re.compile(r"`([^`\n]+)`")
_RE_BARE = re.compile(r"(?<![\w`(/@])([\w.-]+/[\w./-]+)")

# A line that DESCRIBES a path's absence is not a broken pointer — it is documentation
# about the absence. "`ci_gate.py` is NOT inherited here" mentions the path to say it is
# gone, and grading it as a dead reference is the crying-wolf false positive the review
# caught. If the line negates near the pointer, the missing path is intentional.
_NEGATION = re.compile(
    r"\b(not|no longer|never|isn'?t|aren'?t|was|were|used to|removed|deleted|dropped|"
    r"vendored|absent|missing|gone|moved to|renamed|instead of|replaced by|superseded)\b",
    re.I,
)


@dataclass
class Pointer:
    kind: str          # IMPORT / MDLINK / WIKILINK / BACKTICK / BARE
    raw: str           # the token as written
    target: str        # normalized path to test
    line_no: int
    line: str          # the source line, trimmed
    resolved: bool     # did it resolve in the repo
    receipt: str       # why it passed or failed


def _looks_like_path(tok: str) -> bool:
    tok = tok.strip()
    if not tok or _SCHEME.match(tok):
        return False
    if tok.startswith(("#", "mailto:", "tel:")):
        return False
    if "/" in tok:
        return True
    return tok.lower().endswith(_CODE_EXT)


def _norm(target: str) -> str:
    t = target.strip().strip("'\"").split("#", 1)[0].split("?", 1)[0]
    if t.startswith("./"):
        t = t[2:]
    return t.lstrip("/")


def _exists(repo_root: str, rel: str) -> bool:
    if not rel:
        return False
    # A ~ or absolute path is a cross-repo reference, not an intra-repo pointer: grade
    # it against the real filesystem where it lives. R13 used to join it onto repo_root
    # and call an existing `~/CODE/x` broken — crying wolf on a valid reference.
    if rel.startswith("~"):
        return os.path.exists(os.path.expanduser(rel))
    if os.path.isabs(rel):
        return os.path.exists(rel)
    p = os.path.normpath(os.path.join(repo_root, rel))
    # Stay inside the repo — a pointer that escapes the tree is not a repo pointer.
    if os.path.commonpath([os.path.abspath(p), os.path.abspath(repo_root)]) != os.path.abspath(repo_root):
        return os.path.exists(p)  # absolute/parent pointer: grade literally
    return os.path.exists(p)


def _wikilink_resolves(repo_root: str, name: str) -> bool:
    """A [[Note]] resolves if some `Note.md` exists anywhere in the tree (Obsidian rule)."""
    want = name.strip()
    if not want.lower().endswith(".md"):
        want_md = want + ".md"
    else:
        want_md = want
    want_md = os.path.basename(want_md).lower()
    for _root, _dirs, files in os.walk(repo_root):
        if ".git" in _root:
            continue
        for f in files:
            if f.lower() == want_md:
                return True
    return False


def extract_pointers(text: str, repo_root: str) -> list[Pointer]:
    out: list[Pointer] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, raw: str, target: str, line_no: int, line: str, resolved: bool, receipt: str):
        key = (kind, raw)
        if key in seen:
            return
        # A described absence is not a broken pointer. Only skip the UNRESOLVED case —
        # a resolved pointer on a negating line is still a real, present path. Check the
        # negation in the PROSE AROUND the pointer, not the pointer itself: a file named
        # `missing.yml` or a note `[[Missing Note]]` must not self-trigger the guard.
        if not resolved:
            prose = line.replace(raw, " ").replace(target, " ")
            if _NEGATION.search(prose):
                return
        seen.add(key)
        out.append(Pointer(kind, raw, target, line_no, line.strip()[:160], resolved, receipt))

    for i, line in enumerate(text.splitlines(), 1):
        for m in _RE_IMPORT.finditer(line):
            raw = m.group(1)
            if _looks_like_path(raw):
                rel = _norm(raw)
                ok = _exists(repo_root, rel)
                add("IMPORT", "@" + raw, rel, i, line, ok,
                    "resolved" if ok else f"@import target not in repo: {rel}")
        for m in _RE_MDLINK.finditer(line):
            raw = m.group(1)
            if _looks_like_path(raw) and not _SCHEME.match(raw.strip()):
                rel = _norm(raw)
                ok = _exists(repo_root, rel)
                add("MDLINK", raw, rel, i, line, ok,
                    "resolved" if ok else f"linked path not in repo: {rel}")
        for m in _RE_WIKILINK.finditer(line):
            raw = m.group(1)
            ok = _wikilink_resolves(repo_root, raw)
            add("WIKILINK", f"[[{raw}]]", raw, i, line, ok,
                "resolved" if ok else f"no note named '{raw}(.md)' in repo")
        for m in _RE_BACKTICK.finditer(line):
            raw = m.group(1)
            if _looks_like_path(raw) and " " not in raw.strip():
                rel = _norm(raw)
                ok = _exists(repo_root, rel)
                add("BACKTICK", f"`{raw}`", rel, i, line, ok,
                    "resolved" if ok else f"path in code font not in repo: {rel}")
        for m in _RE_BARE.finditer(line):
            raw = m.group(1)
            if _looks_like_path(raw) and raw.lower().endswith(_CODE_EXT):
                rel = _norm(raw)
                ok = _exists(repo_root, rel)
                add("BARE", raw, rel, i, line, ok,
                    "resolved" if ok else f"bare path not in repo: {rel}")
    return out


def check_pointers(repo_root: str, files: list[str] | None = None) -> dict:
    """Grade every pointer in the repo's instruction files against the live tree.

    Returns a rot.py-shaped result: verdict CLEAN / ROT FOUND / UNMEASURED, plus the
    broken pointers with the exact line and the contradicting repo fact. UNMEASURED
    only when no instruction file with any checkable pointer exists — never a silent
    green (a repo with no pointers to grade is not the same as a clean repo).
    """
    targets: list[str] = []
    if files:
        targets = [f for f in files if os.path.exists(os.path.join(repo_root, f))]
    else:
        targets = [f for f in DEFAULT_INSTRUCTION_FILES
                   if os.path.exists(os.path.join(repo_root, f))]

    pointers: list[Pointer] = []
    read_files: list[str] = []
    for rel in targets:
        try:
            with open(os.path.join(repo_root, rel), encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        read_files.append(rel)
        for p in extract_pointers(text, repo_root):
            p.receipt = f"{rel}:{p.line_no} — {p.receipt}"
            pointers.append(p)

    broken = [p for p in pointers if not p.resolved]
    if not read_files or not pointers:
        verdict = "UNMEASURED"
    else:
        verdict = "ROT FOUND" if broken else "CLEAN"

    return {
        "rid": "R13",
        "name": "Instruction pointers vs repo",
        "verdict": verdict,
        "checked": len(pointers),
        "broken": len(broken),
        "files": read_files,
        "receipts": [
            {"kind": p.kind, "raw": p.raw, "line_no": p.line_no,
             "line": p.line, "receipt": p.receipt}
            for p in broken
        ],
    }


def format_pointers(res: dict) -> str:
    head = f"[{res['rid']}] {res['name']}: {res['verdict']}"
    if res["verdict"] == "UNMEASURED":
        return head + "  (no instruction file with checkable pointers)"
    head += f"  ({res['checked']} checked, {res['broken']} broken)"
    lines = [head]
    for r in res["receipts"]:
        lines.append(f"  ✗ {r['kind']} {r['raw']}  →  {r['receipt']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import sys
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python3 -m helicon.pointers <repo_root> [instruction_file ...]")
        return 2
    repo_root = args[0]
    files = args[1:] or None
    res = check_pointers(repo_root, files)
    print(format_pointers(res))
    return 1 if res["verdict"] == "ROT FOUND" else 0


if __name__ == "__main__":
    raise SystemExit(main())
