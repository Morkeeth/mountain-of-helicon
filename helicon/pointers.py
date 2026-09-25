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
    base: str = ""     # which directory the path resolved against (own dir / repo root / under X/)


def _is_bare_extension(tok: str) -> bool:
    """`.js` or `.ts` names a kind of file. `.env` is a filename and stays a path."""
    t = tok.strip()
    if not re.fullmatch(r"\.[A-Za-z0-9]+", t):
        return False
    if t.lower() == ".env":
        return False
    return t.lower() in _CODE_EXT


def _looks_like_path(tok: str) -> bool:
    tok = tok.strip()
    if not tok or _SCHEME.match(tok):
        return False
    if tok.startswith(("#", "mailto:", "tel:")):
        return False
    if tok == "process.env":
        return False                                   # Node member access, not a `.env` file
    if _is_bare_extension(tok):
        return False                                   # `.js` / `.tsx` with no stem is not a path
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
                  and not any(seg in _VENDORED or seg.startswith(".")
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
        ext = os.path.splitext(segs[-1])[1].lower()
        # `react-dom/server.node` is an npm package subpath. A real `.node` file
        # under a directory that exists still counts, via the directory test below.
        if ext != ".node":
            return True                                # `.fleet/ACK.jsonl`, `src/protocol/v2.rs`
    if segs[0].startswith(".") and _RE_PLAIN_SEGMENT.match(segs[0]):
        return True                                    # `.github/workflows`: dot-dirs are paths
    if rel.endswith("/") and all(_RE_PLAIN_SEGMENT.match(s) for s in segs):
        return True
    first = segs[0]
    if not _RE_PLAIN_SEGMENT.match(first):
        return False
    return any(os.path.isdir(os.path.join(repo_root, a, first)) for a in anchors)


def _glob_suffix_base(repo_root: str, rel: str) -> str | None:
    """Prefix of a non-vendored file whose tail matches *rel* as a glob, or None.
    Empty string means the glob matches at the repo root. A vendored or dot-directory
    copy does not count, the same guard the concrete suffix rule uses."""
    parts = [p for p in rel.rstrip("/").split("/") if p]
    if not parts:
        return None
    _names, _dirs, files = _tree(repo_root)
    prefixes: list[str] = []
    for f in files:
        segs = f.split("/")
        if len(segs) < len(parts) or not _segs_match(parts, segs[-len(parts):]):
            continue
        prefix = segs[:-len(parts)]
        if any(seg in _VENDORED or seg.startswith(".") for seg in prefix):
            continue
        prefixes.append("/".join(prefix))
    if not prefixes:
        return None
    prefixes.sort(key=lambda x: (x.count("/"), x))
    return prefixes[0]


_CASE_STEM = re.compile(
    r"^(?:kebab-case|snake_case|camelCase|PascalCase|SCREAMING_SNAKE_CASE|"
    r"UPPER_SNAKE_CASE|TitleCase)$"
)
_PLACEHOLDER_SEG = re.compile(
    r"^(?:agent-name|category-name|component-name|file-name|class-name|module-name|"
    r"hook-name|page-name|your-name|example-name|placeholder|ComponentName|ClassName|"
    r"FileName|ModuleName|PageName|HookName)$"
)
_USE_CASE = re.compile(r"\bUse (?:kebab-case|snake_case|camelCase|PascalCase)\b")
_CODE_FENCE_LANGS = {
    "json", "javascript", "js", "jsx", "ts", "tsx", "typescript",
    "ruby", "rb", "python", "py", "bash", "sh", "shell", "zsh",
    "go", "rust", "rs", "java", "css", "html", "xml", "yaml", "yml",
    "toml", "sql", "vue", "svelte", "php", "c", "cpp", "cs", "kt",
    "kotlin", "swift", "scss", "less", "graphql",
}


def _stem(part: str) -> str:
    return part.rsplit(".", 1)[0] if "." in part else part


def _naming_or_placeholder(tok: str, line: str) -> bool:
    """True when *tok* is a naming pattern or a placeholder, not a repo path.

    `kebab-case.js` and `ComponentName/ComponentName.tsx` are the pattern itself.
    `Use snake_case (`user_profile.py`)` is an illustration, and only when the
    token has no directory: `src/user_profile.py` on that line is still a path.
    """
    body = tok.strip().strip("`").strip("'\"")
    if not body or " " in body:
        return False
    parts = [p for p in body.rstrip("/").split("/") if p]
    if not parts:
        return False
    if any(_PLACEHOLDER_SEG.fullmatch(_stem(p)) for p in parts):
        return True
    if _CASE_STEM.fullmatch(_stem(parts[-1])):
        return True
    if "/" not in body and _USE_CASE.search(line):
        return True
    return False


def _code_example_lines(text: str) -> set[int]:
    """Line numbers inside a fenced JSON or code example.

    An untagged fence and a markdown fence stay graded. Those hold real
    instruction paths (`review some/file.md`, `.loki/queue/pending.json`).
    """
    inside = False
    skip = False
    out: set[int] = set()
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            if not inside:
                info = stripped[3:].strip().split()
                lang = info[0].lower().split("{", 1)[0] if info else ""
                skip = lang in _CODE_FENCE_LANGS
                inside = True
            else:
                inside = False
                skip = False
            continue
        if inside and skip:
            out.add(i)
    return out


def _parent_relative(line: str, raw: str, repo_root: str, file_dir: str,
                     learned: tuple[str, ...]) -> tuple[str, bool, str] | None:
    """Resolve a directory listed inside parentheses against a parent directory
    named earlier on the same line. `src/` (`cli/`, `config/`) means `src/cli`.
    A child that does not exist under that parent stays unresolved."""
    child = raw.strip().strip("`").strip("'\"")
    if not re.fullmatch(r"[\w.-]+/", child):
        return None
    pos = line.find(f"`{child}`")
    if pos < 0:
        return None
    before = line[:pos]
    open_paren = before.rfind("(")
    if open_paren < 0 or before.rfind(")") > open_paren:
        return None
    parents = re.findall(r"`([\w.-]+/)`", line[:open_paren])
    if not parents:
        return None
    return _resolve(repo_root, parents[-1] + child, file_dir, learned)


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
    if re.search(r"\$[A-Za-z_]", tok):
        return None                                    # `$SUPERSET_HOME_DIR/plugins/...` is not a repo path
    if tok.startswith("@") and not tok.lower().endswith(_CODE_EXT) and not _exists(repo_root, _norm(tok[1:])):
        return None                                    # `@typescript-eslint/no-explicit-any` is an npm scope
    if _RE_HOSTNAME.match(tok.split("/", 1)[0]) and not tok.split("/", 1)[0].lower().endswith(_CODE_EXT):
        return None                                    # relay.vercel.app/api/… is a URL
    if _RE_SLASH_COMMAND.match(tok):
        name = tok[1:]                                 # `/notebook-review` is a Claude Code command
        for cand in (f".claude/commands/{name}.md", f".claude/skills/{name}/SKILL.md",
                     f".claude/skills/{name}"):
            if os.path.exists(os.path.join(repo_root, cand)):
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
    if "*" in rel or "?" in rel:
        import glob as _glob                            # `contracts/src/FavourEscrowV2*.sol`
        for b, label in bases:
            if _glob.glob(os.path.join(repo_root, b, rel)):
                return rel, True, label
        suffix = _glob_suffix_base(repo_root, rel)
        if suffix is not None:
            where = f"{suffix}/" if suffix else "repo root"
            # Not "under": that label is learned as an anchor and would grade new tokens.
            return rel, True, f"glob suffix {where}"
        if not _has_path_evidence(repo_root, rel, anchors):
            return None                                 # `rawResponseItem/*` is an event family
        return rel, False, ""
    for b, label in bases:
        if _exists(repo_root, _join(b, rel) if b else rel):
            return rel, True, label
    names, dirs, files = _tree(repo_root)
    if "/" not in rel:                                 # `campaign-unlock.ts` names a file, not a root path
        return rel, rel.lower() in names, "basename anywhere in tree"
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
    try:
        with open(os.path.join(root, "package.json"), encoding="utf-8") as fh:
            ws = _json.load(fh).get("workspaces")
        if isinstance(ws, dict):
            ws = ws.get("packages")
        if isinstance(ws, list):
            pats += [w for w in ws if isinstance(w, str)]
    except (OSError, ValueError, AttributeError):
        pass
    try:
        with open(os.path.join(root, "pnpm-workspace.yaml"), encoding="utf-8") as fh:
            in_pkgs = False
            for line in fh:
                if re.match(r"^packages\s*:", line):
                    in_pkgs = True
                    continue
                if in_pkgs:
                    m = re.match(r"^\s+-\s*['\"]?([^'\"#]+?)['\"]?\s*(#.*)?$", line)
                    if m:
                        pats.append(m.group(1).strip())
                    elif line.strip() and not line.startswith((" ", "\t")):
                        in_pkgs = False
    except OSError:
        pass
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
          if not any(seg in _VENDORED or seg.startswith(".") for seg in w.split("/"))]
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
    try:
        with open(os.path.join(root, ".gitignore"), encoding="utf-8", errors="replace") as fh:
            for line in fh:
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
    except OSError:
        pass
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
    return bool(path) and fnmatch.fnmatchcase(path[0], pat[0]) and _segs_match(pat[1:], path[1:])


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
        if not ok:
            adopted = _parent_relative(line, raw, repo_root, file_dir, learned)
            if adopted and adopted[1]:
                target, ok, base = adopted
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

    code_lines = _code_example_lines(text)
    for i, line in enumerate(text.splitlines(), 1):
        if i in code_lines:
            continue
        for m in _RE_IMPORT.finditer(line):
            raw = m.group(1)
            if _inside_flag(line, m.start()):
                continue                               # `--conditions=@zod/source` is a flag value
            # An @import is a file. `@typescript-eslint/no-explicit-any` is an npm scope:
            # no extension and nothing on disk → not an import, not graded.
            if _looks_like_path(raw):
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
                if _naming_or_placeholder(raw, line):
                    continue
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
                if _naming_or_placeholder(raw, line):
                    continue
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


def nested_instruction_files(repo_root: str) -> list[str]:
    """AGENTS.md / CLAUDE.md below the repo root, outside vendored trees."""
    _names, _dirs, files = _tree(repo_root)
    out = []
    for f in files:
        if "/" not in f or os.path.basename(f).lower() not in _NESTED_NAMES:
            continue
        if any(seg in _VENDORED or seg.startswith(".") for seg in f.split("/")[:-1]):
            continue
        out.append(f)
    return sorted(out)


def instruction_files(repo_root: str, files: list[str] | None = None,
                      nested: bool = False) -> tuple[list[str], dict[str, list[str]]]:
    """The instruction files to grade, one per real file on disk.

    zod ships CLAUDE.md and .cursorrules as symlinks to AGENTS.md. Graded as three files,
    every finding printed three times and the grade counted each claim three times. Files
    in the same directory are deduped by resolved real path. The canonical name is the entry that is not a
    symlink (else the first seen); the others are returned as its aliases."""
    if files:
        cands = [f for f in files if os.path.exists(os.path.join(repo_root, f))]
    else:
        cands = [f for f in DEFAULT_INSTRUCTION_FILES
                 if os.path.exists(os.path.join(repo_root, f))]
        if nested:
            cands += nested_instruction_files(repo_root)
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
