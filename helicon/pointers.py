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
# 2026-09-03: the lookbehind must also refuse '-', '.' and '~'. Without them the match
# started mid-token — `truth-dictionary/aliases.json` was graded as `dictionary/aliases.json`,
# `mcp-server/README.md` as `server/README.md`, `~/.helicon/config.json` as
# `helicon/config.json` — and every one of those was reported broken against a repo that
# had the real file. Ran on the author's own six repos: 21 of 24 findings were this.
_RE_BARE = re.compile(r"(?<![\w`(/@~.-])([\w.-]+/[\w./-]+)")
_RE_CODESPAN = re.compile(r"`[^`\n]*`")
_RE_SLASH_COMMAND = re.compile(r"^/[\w-]+$")
_RE_HOSTNAME = re.compile(r"^[\w-]+(\.[\w-]+)+$")
_PLACEHOLDER = ("<", ">", "{", "}", "YYYY", "…", "...")

# A line that DESCRIBES a path's absence is not a broken pointer — it is documentation
# about the absence. "`ci_gate.py` is NOT inherited here" mentions the path to say it is
# gone, and grading it as a dead reference is the crying-wolf false positive the review
# caught. If the line negates near the pointer, the missing path is intentional.
_NEGATION = re.compile(
    r"\b(not|no longer|never|isn'?t|aren'?t|was|were|used to|removed|deleted|dropped|"
    r"vendored|absent|missing|gone|moved to|renamed|instead of|replaced by|superseded)\b",
    re.I,
)

# A missing target can be intentional when the instruction itself creates it. Keep
# these visible, but do not grade the pre-run absence as a broken repo reference.
# Require a directional preposition so prose such as "write the beat, rows in
# `todo.md`" does not hide a genuinely unresolved pointer.
_WRITE_TARGET = re.compile(
    r"\b(append|create|emit|generate|save|write)\b.*\b(to|into|as)\b",
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


_TREE_CACHE: dict[str, tuple[set[str], list[str], list[str]]] = {}


def _tree(repo_root: str) -> tuple[set[str], list[str], list[str]]:
    """One walk per repo: lower-cased basenames, relative dir paths, relative file paths."""
    root = os.path.abspath(repo_root)
    hit = _TREE_CACHE.get(root)
    if hit is not None:
        return hit
    names: set[str] = set()
    dirs: list[str] = []
    files: list[str] = []
    for r, ds, fs in os.walk(root):
        ds[:] = [d for d in ds if d not in (".git", "node_modules", "__pycache__", ".venv", "venv")]
        rel = os.path.relpath(r, root).replace(os.sep, "/")
        for d in ds:
            dirs.append(d if rel == "." else f"{rel}/{d}")
        for f in fs:
            names.add(f.lower())
            files.append(f if rel == "." else f"{rel}/{f}")
    _TREE_CACHE[root] = (names, dirs, files)
    return _TREE_CACHE[root]


def _resolve(repo_root: str, raw: str) -> tuple[str, bool] | None:
    """Classify a path-shaped token. Returns (target, resolved) or None when the token
    is not something a repo tree can grade — a slash command that is not a file, an npm
    scope, a URL route, a hostname, a template. Each skip is a class the 2026-09-03 run on
    the author's own repos graded as a dead pointer while the thing it named existed."""
    tok = raw.strip().strip("'\"")
    if not tok or any(m in tok for m in _PLACEHOLDER):
        return None                                    # `<username>/<feature>` is a template
    if tok.startswith("@") and not tok.lower().endswith(_CODE_EXT) and not _exists(repo_root, _norm(tok[1:])):
        return None                                    # `@typescript-eslint/no-explicit-any` is an npm scope
    if _RE_HOSTNAME.match(tok.split("/", 1)[0]) and not tok.split("/", 1)[0].lower().endswith(_CODE_EXT):
        return None                                    # relay.vercel.app/api/… is a URL
    if _RE_SLASH_COMMAND.match(tok):
        name = tok[1:]                                 # `/notebook-review` is a Claude Code command
        for cand in (f".claude/commands/{name}.md", f".claude/skills/{name}/SKILL.md",
                     f".claude/skills/{name}"):
            if os.path.exists(os.path.join(repo_root, cand)):
                return cand, True
        return None                                    # built-in or harness command: not gradable here
    rel = _norm(tok)
    if "*" in rel or "?" in rel:
        import glob as _glob                            # `contracts/src/FavourEscrowV2*.sol`
        return rel, bool(_glob.glob(os.path.join(repo_root, rel)))
    # Host paths are outside the repository population. Record their current host
    # status separately, but never let them change the repo grade's denominator.
    if _machine_local(tok):
        return None
    if _exists(repo_root, rel):
        return rel, True
    names, dirs, files = _tree(repo_root)
    if "/" not in rel:                                 # `campaign-unlock.ts` names a file, not a root path
        return rel, rel.lower() in names
    if tok.startswith("/") and not rel.lower().endswith(_CODE_EXT):
        # `/api/escrow-v2` is route-shaped: resolved if any directory ends with it, else not gradable
        return (rel, True) if any(d == rel or d.endswith("/" + rel) for d in dirs) else None
    return rel, False


def _machine_local(tok: str) -> bool:
    """Whether *tok* names a host path rather than a repository path or URL route."""
    target = tok.strip().strip("'\"")
    if target.startswith("~"):
        return True
    if not os.path.isabs(target):
        return False
    if target.lower().endswith(_CODE_EXT):
        return True
    first = target.split("/", 2)[1] if target.startswith("/") and len(target) > 1 else ""
    return first in {
        "Users", "home", "tmp", "var", "etc", "opt", "private", "root",
        "Volumes", "mnt", "data", "workspace",
    }


def _expected_output(line: str, raw: str) -> bool:
    """True when the prose tells the reader to create the missing target."""
    candidates = (raw, raw.strip("`"))
    positions = [line.find(candidate) for candidate in candidates if candidate and candidate in line]
    if not positions:
        return False
    prefix = line[:min(position for position in positions if position >= 0)]
    return bool(_WRITE_TARGET.search(prefix))


def _exists(repo_root: str, rel: str) -> bool:
    if not rel:
        return False
    # Kept for direct callers. The repo review classifies host paths before this
    # function and excludes them from its grade denominator.
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
    """Return only paths that can be graded against this repo or current host."""
    pointers, _unverified = _extract(text, repo_root)
    return pointers


def extract_unverified_paths(text: str, repo_root: str) -> list[dict]:
    """Return absent external and create-on-demand paths excluded from the grade."""
    _pointers, unverified = _extract(text, repo_root)
    return unverified


def _extract(text: str, repo_root: str) -> tuple[list[Pointer], list[dict]]:
    out: list[Pointer] = []
    unverified: list[dict] = []
    seen: set[tuple[str, str]] = set()
    seen_unverified: set[tuple[str, str]] = set()

    def note_unverified(kind: str, raw: str, line_no: int, line: str, reason: str):
        key = (kind, raw)
        if key in seen_unverified:
            return
        seen_unverified.add(key)
        unverified.append({
            "kind": kind,
            "raw": raw,
            "line_no": line_no,
            "line": line.strip()[:160],
            "reason": reason,
        })

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

    def grade_path(kind: str, raw: str, display: str, line_no: int, line: str, miss_msg: str):
        resolved = _resolve(repo_root, raw)
        if resolved is None:
            if _machine_local(raw):
                host = raw.strip().strip("'\"")
                host_path = os.path.expanduser(host) if host.startswith("~") else host
                state = "present" if os.path.exists(host_path) else "absent"
                note_unverified(
                    kind, display, line_no, line,
                    f"external path {state} on this host; repo claim not graded",
                )
            return
        target, ok = resolved
        if not ok and _expected_output(line, display):
            note_unverified(
                kind, display, line_no, line,
                "instruction creates this path; pre-run absence not graded",
            )
            return
        add(kind, display, target, line_no, line, ok,
            "resolved" if ok else miss_msg.format(target=target))

    for i, line in enumerate(text.splitlines(), 1):
        for m in _RE_IMPORT.finditer(line):
            raw = m.group(1)
            # An @import is a file. `@typescript-eslint/no-explicit-any` is an npm scope:
            # no extension and nothing on disk → not an import, not graded.
            if _looks_like_path(raw):
                r = _resolve(repo_root, raw)
                if r is None or (not r[1] and not raw.lower().endswith(_CODE_EXT)):
                    continue
                rel, ok = r
                add("IMPORT", "@" + raw, rel, i, line, ok,
                    "resolved" if ok else f"@import target not in repo: {rel}")
        for m in _RE_MDLINK.finditer(line):
            raw = m.group(1)
            if _looks_like_path(raw) and not _SCHEME.match(raw.strip()):
                grade_path("MDLINK", raw, raw, i, line,
                           "linked path not in repo: {target}")
        for m in _RE_WIKILINK.finditer(line):
            raw = m.group(1)
            ok = _wikilink_resolves(repo_root, raw)
            add("WIKILINK", f"[[{raw}]]", raw, i, line, ok,
                "resolved" if ok else f"no note named '{raw}(.md)' in repo")
        for m in _RE_BACKTICK.finditer(line):
            raw = m.group(1)
            if _looks_like_path(raw) and " " not in raw.strip():
                grade_path("BACKTICK", raw, f"`{raw}`", i, line,
                           "path in code font not in repo: {target}")
        # Code spans were graded above; scanning them again as bare prose is how
        # `~/.zen/zup-active.json` produced a second, mangled pointer `zen/zup-active.json`.
        for m in _RE_BARE.finditer(_RE_CODESPAN.sub(" ", line)):
            raw = m.group(1).rstrip(".-")
            if _looks_like_path(raw) and raw.lower().endswith(_CODE_EXT):
                grade_path("BARE", raw, raw, i, line,
                           "bare path not in repo: {target}")
    return out, unverified


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
    unverified_paths: list[dict] = []
    read_files: list[str] = []
    for rel in targets:
        try:
            with open(os.path.join(repo_root, rel), encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        read_files.append(rel)
        extracted, unverified = _extract(text, repo_root)
        for p in extracted:
            p.receipt = f"{rel}:{p.line_no} — {p.receipt}"
            pointers.append(p)
        for gap in unverified:
            gap["file"] = rel
            unverified_paths.append(gap)

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
        "unverified_paths": unverified_paths,
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
