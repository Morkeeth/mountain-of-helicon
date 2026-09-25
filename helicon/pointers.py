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

from helicon.nofollow import SafeOpenError, open_nofollow

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
_RE_IMPORT = re.compile(r"(?<![`\w])@([~\w./-]+)")
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
    base: str = ""     # which directory the path resolved against (own dir / repo root / under X/)


def _looks_like_path(tok: str) -> bool:
    tok = tok.strip()
    if not tok or _SCHEME.match(tok):
        return False
    if tok.startswith(("#", "mailto:", "tel:")):
        return False
    if not re.search(r"\w", tok):
        return False                                   # `//` is a comment marker, not a path
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


# Where a relative path was found. Recorded on every pointer so a reader can see
# which directory the check resolved against, not just that it resolved.
BASE_OWN = "own dir"        # the directory holding the instruction file
BASE_ROOT = "repo root"     # fallback when the own dir does not have it
BASE_SUFFIX = "under"       # found as a suffix of a real tree path, e.g. under codex-rs/
BASE_PKG = "package"        # found relative to a monorepo package, e.g. package packages/zod/src/v4/

# `/*param_name*/` is a Rust/C comment, not a path. Neither is a glob whose first
# segment is not a plain name.
_RE_PLAIN_SEGMENT = re.compile(r"^[\w.-]+$")
_RE_FILE_EXT = re.compile(r"[\w-]\.[A-Za-z][A-Za-z0-9]{0,7}$")


def _join(*parts: str) -> str:
    return "/".join(p.strip("/") for p in parts if p and p.strip("/"))


def _suffix_prefixes(repo_root: str, rel: str) -> list[str]:
    """Tree prefixes P such that P/rel exists. Only multi-segment paths qualify: a
    single name matching somewhere is the basename rule, not a location."""
    rel = rel.rstrip("/")
    if "/" not in rel:
        return []
    _names, dirs, files = _tree(repo_root)
    tail = "/" + rel
    # A fixture or vendored copy is not where this repo keeps the path. Without this
    # guard a stale root pointer goes green because tests/fixtures/ holds a copy.
    out = sorted({e[: -len(tail)] for e in (*dirs, *files) if e.endswith(tail)
                  and not any(_segment_excluded(seg)
                              for seg in e[: -len(tail)].split("/"))},
                 key=lambda x: (x.count("/"), x))
    return out


def _has_path_evidence(repo_root: str, rel: str, anchors: tuple[str, ...]) -> bool:
    """Is an UNRESOLVED slash token a path at all? `thread/read` and `app/list` are
    RPC method names; `rawResponseItem/*` is an event family. Grade a miss only when
    the token carries evidence of being a path:
      - a known code extension (`src/protocol/v2.rs`),
      - a trailing slash on plain names (`docs/old/`),
      - its first segment is a real directory under an anchor (the file's own dir,
        the repo root, or a base another pointer in the same file resolved under).
    Anchored, never anywhere-in-tree: codex has `codex-rs/tui/src/app`, and an
    anywhere rule would keep `app/list` red."""
    body = rel.rstrip("/")
    if not body:
        return False
    segs = body.split("/")
    if _RE_FILE_EXT.search(segs[-1]) and "*" not in segs[0]:
        return True                                    # `.fleet/ACK.jsonl`, `src/protocol/v2.rs`
    if segs[0].startswith(".") and _RE_PLAIN_SEGMENT.match(segs[0]):
        return True                                    # `.github/workflows`: dot-dirs are paths
    if rel.endswith("/") and all(_RE_PLAIN_SEGMENT.match(s) for s in segs):
        return True
    first = segs[0]
    if not _RE_PLAIN_SEGMENT.match(first):
        return False
    root = os.path.realpath(repo_root)
    return any(_is_dir_inside(root, _join(a, first) if a else first) for a in anchors)


def _resolve(repo_root: str, raw: str, file_dir: str = "",
             learned: tuple[str, ...] = ()) -> tuple[str, bool, str] | None:
    """Classify a path-shaped token. Returns (target, resolved, base) or None when the
    token is not something a repo tree can grade — a slash command that is not a file,
    an npm scope, a URL route, a hostname, a template, an RPC name, a comment. Each skip
    is a class a real run graded as a dead pointer while the thing it named existed.

    Resolution order (2026-09-24, openai/codex false positives):
      1. the instruction file's own directory,
      2. the repo root,
      3. a suffix of a real tree path (`app-server-protocol/src/protocol/v2/` under
         `codex-rs/`, where the root AGENTS.md says "In the codex-rs folder").
    `base` names which one matched."""
    tok = raw.strip().strip("'\"")
    if not tok or any(m in tok for m in _PLACEHOLDER):
        return None                                    # `<username>/<feature>` is a template
    if tok.startswith("-"):
        return None                                    # `--conditions=@zod/source` is a CLI flag
    if not _norm(tok).strip("/") or not re.search(r"\w", tok):
        return None                                    # `//` normalizes to nothing: no target to grade
    if tok.startswith("/*") or tok.endswith("*/"):
        return None                                    # `/*param_name*/` is a code comment
    if tok.startswith("@") and not tok.lower().endswith(_CODE_EXT) and not _exists(repo_root, _norm(tok[1:])):
        return None                                    # `@typescript-eslint/no-explicit-any` is an npm scope
    if _RE_HOSTNAME.match(tok.split("/", 1)[0]) and not tok.split("/", 1)[0].lower().endswith(_CODE_EXT):
        return None                                    # relay.vercel.app/api/… is a URL
    if _RE_SLASH_COMMAND.match(tok):
        name = tok[1:]                                 # `/notebook-review` is a Claude Code command
        for cand in (f".claude/commands/{name}.md", f".claude/skills/{name}/SKILL.md",
                     f".claude/skills/{name}"):
            if _exists(repo_root, cand):
                return cand, True, BASE_ROOT
        return None                                    # built-in or harness command: not gradable here
    # Host paths are outside the repository population. Record their current host
    # status separately, but never let them change the repo grade's denominator.
    if _machine_local(tok):
        return None
    rel = _norm(tok)
    file_dir = file_dir.strip("/")
    bases: list[tuple[str, str]] = []
    if file_dir:
        bases.append((file_dir, f"{BASE_OWN} {file_dir}/"))
    bases.append(("", BASE_ROOT))
    anchors = tuple(dict.fromkeys([file_dir, "", *learned]))

    def placed(base: str) -> str | None:
        combined = os.path.normpath(os.path.join(base, rel) if base else rel).replace(os.sep, "/")
        if (not combined or combined in (".", "..") or combined.startswith("../")
                or os.path.isabs(combined)):
            return None
        return combined

    escaped = False
    if "*" in rel or "?" in rel:
        import glob as _glob                            # `contracts/src/FavourEscrowV2*.sol`
        root = os.path.realpath(repo_root)
        for b, label in bases:
            combined = placed(b)
            if combined is None:
                escaped = True
                continue
            for hit in _glob.glob(os.path.join(root, *combined.split("/"))):
                rel_hit = os.path.relpath(hit, root).replace(os.sep, "/")
                if not rel_hit.startswith("../") and _exists(repo_root, rel_hit):
                    return rel, True, label
        if escaped:
            return rel, False, "outside the repo"
        if not _has_path_evidence(repo_root, rel, anchors):
            return None                                 # `rawResponseItem/*` is an event family
        return rel, False, ""
    for b, label in bases:
        combined = placed(b)
        if combined is None:
            escaped = True
            continue
        if _exists(repo_root, combined):
            return rel, True, label
    if escaped:
        return rel, False, "outside the repo"
    names, dirs, files = _tree(repo_root)
    if "/" not in rel:                                 # `config.py` is a root path, not a search
        if _exists(repo_root, rel):
            return rel, True, BASE_ROOT
        hits = [f for f in files if "/" in f and os.path.basename(f).casefold() == rel.casefold()]
        if hits:
            hint = sorted(hits, key=lambda f: (f.count("/"), len(f), f))[0]
            return rel, False, f"deeper {hint}"
        return rel, False, ""
    if tok.startswith("/") and not rel.lower().endswith(_CODE_EXT):
        # `/api/escrow-v2` is route-shaped: resolved if any directory ends with it, else not gradable
        return (rel, True, "route suffix in tree") if any(
            d == rel or d.endswith("/" + rel) for d in dirs) else None
    prefixes = _suffix_prefixes(repo_root, rel)
    if prefixes:
        own = [p for p in prefixes if not file_dir or p == file_dir or p.startswith(file_dir + "/")]
        pick = (own or prefixes)[0]
        return rel, True, f"{BASE_SUFFIX} {pick}/"
    # Monorepo: a root doc names `core/` or `src/` relative to a package, not the root.
    # A single segment has no tail for the suffix rule above, so it lands here.
    # Try the bases this file's other paths resolved under, then each workspace package
    # (package.json `workspaces`, pnpm-workspace.yaml), then its src/.
    for b in _package_bases(repo_root, learned):
        for pb in (b, _join(b, "src")):
            if _exists(repo_root, _join(pb, rel)):
                return rel, True, f"{BASE_PKG} {pb}/"
    if not _has_path_evidence(repo_root, rel, anchors):
        return None                                    # `thread/read` is an RPC name, not a path
    return rel, False, ""


_WS_CACHE: dict[str, tuple[str, ...]] = {}


def workspace_dirs(repo_root: str) -> tuple[str, ...]:
    """Workspace package directories declared by the repo: package.json `workspaces`
    (a list, or `{"packages": [...]}`) and pnpm-workspace.yaml `packages:`. Globs are
    expanded against the tree; only existing directories are kept."""
    root = os.path.abspath(repo_root)
    hit = _WS_CACHE.get(root)
    if hit is not None:
        return hit
    import glob as _glob
    import json as _json
    pats: list[str] = []
    raw = read_repo_text(root, "package.json")
    if raw:
        try:
            ws = _json.loads(raw).get("workspaces")
            if isinstance(ws, dict):
                ws = ws.get("packages")
            if isinstance(ws, list):
                pats += [w for w in ws if isinstance(w, str)]
        except (ValueError, AttributeError):
            pass
    raw = read_repo_text(root, "pnpm-workspace.yaml")
    if raw:
        in_pkgs = False
        for line in raw.splitlines():
            if re.match(r"^packages\s*:", line):
                in_pkgs = True
                continue
            if in_pkgs:
                m = re.match(r"^\s+-\s*['\"]?([^'\"#]+?)['\"]?\s*(#.*)?$", line)
                if m:
                    pats.append(m.group(1).strip())
                elif line.strip() and not line.startswith((" ", "\t")):
                    in_pkgs = False
    out: list[str] = []
    for pat in pats:
        if pat.startswith("!"):
            continue
        for d in sorted(_glob.glob(os.path.join(root, pat.strip("/")))):
            if os.path.isdir(d):
                rel = os.path.relpath(d, root).replace(os.sep, "/")
                if rel not in out and not rel.startswith(".."):
                    out.append(rel)
    _WS_CACHE[root] = tuple(out)
    return _WS_CACHE[root]


def _package_bases(repo_root: str, learned: tuple[str, ...] = ()) -> list[str]:
    """Learned bases first, then workspace packages. A vendored, fixture, bench or
    dot-directory package is not where this repo keeps its paths, the same guard the
    suffix rule applies."""
    ws = [w for w in workspace_dirs(repo_root)
          if not any(_segment_excluded(seg) for seg in w.split("/"))]
    return list(dict.fromkeys([b for b in (*learned, *ws) if b]))


_IGNORE_CACHE: dict[str, list[tuple[bool, list[str], bool, bool]]] = {}


def _gitignore_rules(repo_root: str) -> list[tuple[bool, list[str], bool, bool]]:
    """(negated, segments, dir_only, anchored) from the repo's root .gitignore, in file
    order. A small parser, not git: a fixture checked in under another repo must be
    judged by its own .gitignore."""
    root = os.path.abspath(repo_root)
    hit = _IGNORE_CACHE.get(root)
    if hit is not None:
        return hit
    rules: list[tuple[bool, list[str], bool, bool]] = []
    text = read_repo_text(root, ".gitignore")
    if text:
        for line in text.splitlines():
            pat = line.strip()
            if not pat or pat.startswith("#"):
                continue
            negated = pat.startswith("!")
            pat = pat[1:] if negated else pat
            dir_only = pat.endswith("/")
            pat = pat.rstrip("/")
            anchored = "/" in pat
            segs = [x for x in pat.lstrip("/").split("/") if x]
            if segs:
                rules.append((negated, segs, dir_only, anchored))
    _IGNORE_CACHE[root] = rules
    return rules


def _segs_match(pat: list[str], path: list[str]) -> bool:
    """Match path segments against pattern segments. `*` never crosses a `/`;
    `**` matches any number of segments."""
    import fnmatch
    if not pat:
        return not path
    if pat[0] == "**":
        return any(_segs_match(pat[1:], path[i:]) for i in range(len(path) + 1))
    return bool(path) and fnmatch.fnmatchcase(path[0].casefold(), pat[0].casefold()) and _segs_match(pat[1:], path[1:])


def is_gitignored(repo_root: str, rel: str) -> bool:
    """Does the repo's root .gitignore cover *rel* or one of its parent directories?
    A gitignored path is created on demand; a fresh clone never has it. The last
    matching rule wins, so `!docs/GONE.md` re-includes a path and keeps it graded."""
    is_dir = rel.endswith("/")
    segs = [x for x in rel.strip("/").split("/") if x]
    if not segs:
        return False
    ignored = False
    for negated, pat, dir_only, anchored in _gitignore_rules(repo_root):
        hit = False
        for i in range(1, len(segs) + 1):
            # A dir-only rule (`build/`) matches a parent directory, or the target
            # itself only when the doc writes it as a directory.
            if dir_only and i == len(segs) and not is_dir:
                continue
            prefix = segs[:i]
            if anchored:
                hit = _segs_match(pat, prefix)
            else:
                hit = len(pat) == 1 and _segs_match(pat, prefix[-1:])
            if hit:
                break
        if hit:
            ignored = not negated
    return ignored


def _import_outside_target(raw: str, file_dir: str) -> str | None:
    """Lexical @import target when it leaves the repo, else None.

    '~' and a leading '/' are outside without expansion: expanding or stating
    them would read a host file. A relative target, including one that starts
    with '../', is outside only after it is joined to the instruction file's
    directory and normalized. An npm scope has none of these shapes.
    This function does not expand '~' and does not stat.
    """
    tok = raw.strip().strip("'\"")
    if not tok:
        return None
    if tok.startswith("~") or tok.startswith("/") or os.path.isabs(tok):
        return tok
    file_dir = file_dir.strip().strip("/")
    body = tok[2:] if tok.startswith("./") else tok
    combined = os.path.normpath(os.path.join(file_dir, body) if file_dir else body)
    combined = combined.replace(os.sep, "/")
    if combined == ".." or combined.startswith("../") or os.path.isabs(combined):
        return combined
    return None


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


def _stays_inside(root: str, path: str) -> bool:
    """True when path, after resolving existing parents, is still under root.

    root and path are absolute. The final component is not opened.
    """
    root = os.path.realpath(root)
    parent = os.path.abspath(path)
    while not os.path.exists(parent):
        nxt = os.path.dirname(parent)
        if nxt == parent:
            break
        parent = nxt
    suffix = ""
    ab = os.path.abspath(path)
    if ab.startswith(parent):
        suffix = ab[len(parent):]
    canon = os.path.realpath(parent) + suffix
    try:
        return os.path.commonpath([root, canon]) == root
    except ValueError:
        return False


def _walk_inside(root: str, rel: str, *, _depth: int = 0) -> str | None:
    """Absolute path of rel under root, or None if it is missing or leaves root.

    A symlink is followed only when its own target stays inside root. The
    target file is not opened.
    """
    if _depth > 16:
        return None
    cur = root
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    for i, part in enumerate(parts):
        if part == "..":
            return None
        nxt = os.path.join(cur, part)
        if not os.path.lexists(nxt):
            return None
        if os.path.islink(nxt):
            raw = os.readlink(nxt)
            target = os.path.normpath(raw if os.path.isabs(raw) else os.path.join(cur, raw))
            if not _stays_inside(root, target):
                return None
            rest = "/".join(parts[i + 1:])
            rel_target = os.path.relpath(os.path.abspath(target), root).replace(os.sep, "/")
            if rel_target.startswith("../"):
                return None
            return _walk_inside(root, f"{rel_target}/{rest}" if rest else rel_target, _depth=_depth + 1)
        cur = nxt
    return cur


def _is_dir_inside(root: str, rel: str) -> bool:
    found = _walk_inside(root, rel)
    return bool(found) and os.path.isdir(found)


def _exists(repo_root: str, rel: str) -> bool:
    if not rel:
        return False
    # Host paths are classified before a repo grade. They are not repo pointers.
    if rel.startswith("~"):
        return os.path.exists(os.path.expanduser(rel))
    if os.path.isabs(rel):
        return os.path.exists(rel)
    return _walk_inside(os.path.realpath(repo_root), rel) is not None


def _symlink_leaves_repo(repo_root: str, rel: str) -> bool:
    """True when rel is a symlink whose chain resolves outside repo_root.

    Each hop is read with readlink. The target file is not opened.
    """
    root = os.path.realpath(repo_root)
    path = os.path.join(root, rel)
    seen: set[str] = set()
    for _ in range(16):
        if path in seen:
            return True
        seen.add(path)
        if not os.path.islink(path):
            return not _stays_inside(root, path)
        raw = os.readlink(path)
        path = os.path.normpath(raw if os.path.isabs(raw) else os.path.join(os.path.dirname(path), raw))
        if not _stays_inside(root, path):
            return True
    return True


def read_repo_text(repo_root: str, rel: str) -> str | None:
    """Read a text file that stays inside repo_root.

    A symlink that resolves outside is not read. A symlink that stays inside
    is read at its in-repo target, so one file linked from a second name is
    still graded. Returns None when the path cannot be read.
    """
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not rel or os.path.isabs(rel) or rel == ".." or rel.startswith("../"):
        return None
    path = os.path.join(repo_root, rel)
    if os.path.islink(path):
        if _symlink_leaves_repo(repo_root, rel):
            return None
        root = os.path.realpath(repo_root)
        target = os.path.realpath(path)
        rel = os.path.relpath(target, root).replace(os.sep, "/")
        if not rel or rel.startswith("../"):
            return None
    try:
        with open_nofollow(repo_root, rel) as fh:
            return fh.read()
    except (SafeOpenError, OSError, UnicodeDecodeError):
        return None


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


def _inside_flag(line: str, start: int) -> bool:
    """Is the match at *start* part of a CLI flag such as `--conditions=@zod/source`?"""
    head = re.split(r"[\s`(\[]", line[:start])[-1]
    return head.startswith("-")


def extract_pointers(text: str, repo_root: str, file_dir: str = "") -> list[Pointer]:
    """Return only paths that can be graded against this repo or current host."""
    pointers, _unverified = _extract(text, repo_root, file_dir)
    return pointers


def extract_unverified_paths(text: str, repo_root: str, file_dir: str = "") -> list[dict]:
    """Return absent external and create-on-demand paths excluded from the grade."""
    _pointers, unverified = _extract(text, repo_root, file_dir)
    return unverified


def _learned_bases(text: str, repo_root: str, file_dir: str) -> tuple[str, ...]:
    """Directories this file's own resolvable paths live under. codex's root AGENTS.md
    opens "In the codex-rs folder"; its `app-server-protocol/src/protocol/v2/` resolves
    only under codex-rs/, so codex-rs/ becomes an anchor for the path-evidence test of
    every other token in the same file (`core/context` then counts as a path, because
    codex-rs/core is a real directory, and is still graded)."""
    learned: list[str] = []
    for line in text.splitlines():
        toks = [m.group(1) for m in _RE_BACKTICK.finditer(line)]
        toks += [m.group(1) for m in _RE_MDLINK.finditer(line)]
        toks += [m.group(1).rstrip(".-") for m in _RE_BARE.finditer(_RE_CODESPAN.sub(" ", line))]
        for tok in toks:
            tok = tok.strip()
            if "/" not in tok or " " in tok or _SCHEME.match(tok):
                continue
            r = _resolve(repo_root, tok, file_dir)
            if r and r[1] and r[2].startswith(BASE_SUFFIX + " ") and r[2].endswith("/"):
                base = r[2][len(BASE_SUFFIX) + 1:].rstrip("/")
                if base and base not in learned:
                    learned.append(base)
    return tuple(learned)


def _extract(text: str, repo_root: str, file_dir: str = "") -> tuple[list[Pointer], list[dict]]:
    learned = _learned_bases(text, repo_root, file_dir)
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

    def add(kind: str, raw: str, target: str, line_no: int, line: str, resolved: bool, receipt: str,
            base: str = ""):
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
        out.append(Pointer(kind, raw, target, line_no, line.strip()[:160], resolved, receipt, base))

    def grade_path(kind: str, raw: str, display: str, line_no: int, line: str, miss_msg: str):
        resolved = _resolve(repo_root, raw, file_dir, learned)
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
        target, ok, base = resolved
        if base == "outside the repo":
            add(kind, display, target, line_no, line, False,
                f"{display} resolves outside the repo", base)
            return
        if not ok and base.startswith("deeper "):
            hint = base[len("deeper "):]
            add(kind, display, target, line_no, line, False,
                f"{display} is not at the stated path; deeper candidate {hint}", base)
            return
        if not ok and _expected_output(line, display):
            note_unverified(
                kind, display, line_no, line,
                "instruction creates this path; pre-run absence not graded",
            )
            return
        if not ok and is_gitignored(repo_root, _join(file_dir, target) if file_dir else target):
            note_unverified(
                kind, display, line_no, line,
                "gitignored: created on demand, not graded",
            )
            return
        tried = (f"own dir {file_dir}/, repo root" if file_dir else "repo root") + ", tree suffix"
        add(kind, display, target, line_no, line, ok,
            f"resolved from {base}" if ok else miss_msg.format(target=target) + f" (tried {tried})",
            base)

    for i, line in enumerate(text.splitlines(), 1):
        for m in _RE_IMPORT.finditer(line):
            raw = m.group(1)
            if _inside_flag(line, m.start()):
                continue                               # `--conditions=@zod/source` is a flag value
            # An @import is a file. `@typescript-eslint/no-explicit-any` is an npm scope:
            # no extension and nothing on disk → not an import, not graded.
            # That skip must not hide a target that leaves the repo. Report the
            # escape first, whatever the extension, and do not stat the outside file.
            if _looks_like_path(raw):
                outside = _import_outside_target(raw, file_dir)
                if outside is not None:
                    add("IMPORT", "@" + raw, outside, i, line, False,
                        f"@import leaves the repo: {outside}", "outside the repo")
                    continue
                r = _resolve(repo_root, raw, file_dir, learned)
                if r is None or (not r[1] and not raw.lower().endswith(_CODE_EXT)):
                    continue
                rel, ok, base = r
                add("IMPORT", "@" + raw, rel, i, line, ok,
                    f"resolved from {base}" if ok else f"@import target not in repo: {rel}", base)
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
        bare_line = _RE_CODESPAN.sub(" ", line)
        for m in _RE_BARE.finditer(bare_line):
            raw = m.group(1).rstrip(".-")
            if _inside_flag(bare_line, m.start()):
                continue                               # `--out=dist/x.js` is a flag value
            if _looks_like_path(raw) and raw.lower().endswith(_CODE_EXT):
                grade_path("BARE", raw, raw, i, line,
                           "bare path not in repo: {target}")
    return out, unverified


# Directory-scoped instruction files. AGENTS.md and CLAUDE.md apply to the folder that
# holds them (codex-rs/tui/src/bottom_pane/AGENTS.md), so their paths are relative to
# that folder. Vendored trees are someone else's instructions.
_NESTED_NAMES = {"agents.md", "claude.md"}
_VENDORED = {"vendor", "third_party", "third-party", "node_modules", "site-packages", "dist", "build",
             # Sample repos: test fixtures and bench repos are broken on purpose
             # (Helicon's own bench/repos/stale-paths/CLAUDE.md is one).
             "fixtures", "testdata", "bench", "benchmarks", "examples", "samples"}
_VENDORED_CF = frozenset(name.casefold() for name in _VENDORED)


def _segment_excluded(seg: str) -> bool:
    """A vendored, sample, or dot directory is not where this repo keeps its paths.

    The name matches regardless of case, so Vendor/ is the same exclusion as vendor/.
    """
    return seg.startswith(".") or seg.casefold() in _VENDORED_CF


def nested_instruction_files(repo_root: str) -> list[str]:
    """AGENTS.md / CLAUDE.md below the repo root, outside vendored trees."""
    _names, _dirs, files = _tree(repo_root)
    out = []
    for f in files:
        if "/" not in f or os.path.basename(f).lower() not in _NESTED_NAMES:
            continue
        if any(_segment_excluded(seg) for seg in f.split("/")[:-1]):
            continue
        out.append(f)
    return sorted(out)


def _instruction_candidates(repo_root: str, files: list[str] | None,
                           nested: bool) -> list[str]:
    if files:
        cands = [f for f in files if os.path.lexists(os.path.join(repo_root, f))]
    else:
        cands = [f for f in DEFAULT_INSTRUCTION_FILES
                 if os.path.lexists(os.path.join(repo_root, f))]
        if nested:
            cands += nested_instruction_files(repo_root)
    seen: list[str] = []
    for rel in cands:
        if rel not in seen:
            seen.append(rel)
    return seen


REFUSED_SYMLINK_REASON = "refused: symlink resolves outside the repo"


def refusal_for(repo_root: str, rel: str) -> dict | None:
    """The review refusal row when rel resolves outside repo_root, else None.

    Same reason refused_instruction_files reports. The target is not opened.
    A path that stays inside, including an in-repo symlink, returns None.
    """
    rel = (rel or "").strip().replace("\\", "/")
    if rel.startswith("./"):
        rel = rel[2:]
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts or os.path.isabs(rel) or any(part == ".." for part in parts):
        return None
    rel = "/".join(parts)
    if _symlink_leaves_repo(repo_root, rel):
        return {"file": rel, "reason": REFUSED_SYMLINK_REASON}
    return None


def read_contained(repo_root: str, rel: str) -> str | None:
    """Text of rel when its real path stays inside repo_root, else None.

    An outside symlink is not opened. An in-repo file symlink is read at its
    target. An in-repo directory symlink is read at the real path inside the
    repo. Missing and unreadable paths return None.
    """
    if refusal_for(repo_root, rel):
        return None
    text = read_repo_text(repo_root, rel)
    if text is not None:
        return text
    rel = (rel or "").strip().replace("\\", "/")
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    root = os.path.realpath(repo_root)
    candidate = os.path.join(root, *parts)
    if not os.path.lexists(candidate):
        return None
    real = os.path.realpath(candidate)
    try:
        inside = os.path.commonpath([root, real]) == root
    except ValueError:
        inside = False
    if not inside:
        return None
    resolved = os.path.relpath(real, root).replace(os.sep, "/")
    if (
        not resolved
        or resolved == rel
        or resolved.startswith("../")
        or refusal_for(repo_root, resolved)
    ):
        return None
    return read_repo_text(repo_root, resolved)


def refused_instruction_files(repo_root: str, files: list[str] | None = None,
                              nested: bool = False) -> list[dict]:
    """Instruction symlinks whose target resolves outside the repo.

    They are not read. reason contains 'refused' so a review can say so.
    """
    out = []
    for rel in _instruction_candidates(repo_root, files, nested):
        path = os.path.join(repo_root, rel)
        if os.path.islink(path) and _symlink_leaves_repo(repo_root, rel):
            out.append({
                "file": rel,
                "reason": REFUSED_SYMLINK_REASON,
            })
    return out


def instruction_files(repo_root: str, files: list[str] | None = None,
                      nested: bool = False) -> tuple[list[str], dict[str, list[str]]]:
    """The instruction files to grade, one per real file on disk.

    zod ships CLAUDE.md and .cursorrules as symlinks to AGENTS.md. Graded as three files,
    every finding printed three times and the grade counted each claim three times. Files
    in the same directory are deduped by resolved real path. The canonical name is the entry that is not a
    symlink (else the first seen); the others are returned as its aliases.

    A symlink that resolves outside the repo is not a candidate. It is reported
    by refused_instruction_files and is not read.
    """
    refused = {row["file"] for row in refused_instruction_files(repo_root, files, nested)}
    cands = [f for f in _instruction_candidates(repo_root, files, nested) if f not in refused]
    # Key on (directory, real file). Paths resolve from the file's own directory, so
    # one file linked into two directories is two different sets of claims.
    def key(f: str) -> tuple[str, str]:
        return (os.path.dirname(f), os.path.realpath(os.path.join(repo_root, f)))
    groups: dict[tuple[str, str], list[str]] = {}
    for f in cands:
        groups.setdefault(key(f), []).append(f)
    out: list[str] = []
    aliases: dict[str, list[str]] = {}
    for f in cands:
        group = groups[key(f)]
        real = [g for g in group if not os.path.islink(os.path.join(repo_root, g))]
        canon = (real or group)[0]
        if canon != f or canon in out:
            continue
        out.append(canon)
        others = [g for g in group if g != canon]
        if others:
            aliases[canon] = others
    return out, aliases


def check_pointers(repo_root: str, files: list[str] | None = None) -> dict:
    """Grade every pointer in the repo's instruction files against the live tree.

    Returns a rot.py-shaped result: verdict CLEAN / ROT FOUND / UNMEASURED, plus the
    broken pointers with the exact line and the contradicting repo fact. UNMEASURED
    only when no instruction file with any checkable pointer exists — never a silent
    green (a repo with no pointers to grade is not the same as a clean repo).
    """
    targets, aliases = instruction_files(repo_root, files, nested=True)
    refused = refused_instruction_files(repo_root, files, nested=True)

    pointers: list[Pointer] = []
    unverified_paths: list[dict] = []
    read_files: list[str] = []
    for rel in targets:
        text = read_repo_text(repo_root, rel)
        if text is None:
            continue
        read_files.append(rel)
        extracted, unverified = _extract(text, repo_root, os.path.dirname(rel))
        for p in extracted:
            p.receipt = f"{rel}:{p.line_no} — {p.receipt}"
            pointers.append(p)
        for gap in unverified:
            gap["file"] = rel
            unverified_paths.append(gap)

    broken = [p for p in pointers if not p.resolved]
    bases: dict[str, int] = {}
    for p in pointers:
        if p.resolved and p.base:
            bases[p.base] = bases.get(p.base, 0) + 1
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
        "bases": bases,
        "aliases": aliases,
        "refused": refused,
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
