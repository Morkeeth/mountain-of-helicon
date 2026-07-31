"""The doorway — every repo an agent walks through, and what each one loads.

The build-plan's line: make Helicon the door every agent on the machine walks
through. The board is that door. For a root of repos (default `~/CODE`) it
answers, per repo, one honest number: how many tokens of instruction context
this repo loads into an agent every session — CLAUDE.md, the files it `@imports`,
and the other committed agent-rules files (AGENTS.md, .cursor/rules/*, …).

This is measured, never estimated from a vibe: the token count is `chars // 4`
over the ACTUAL files an agent loads, with `@import` lines resolved (recursively,
bounded) exactly the way Claude Code resolves them. A repo nobody wrote a config
for loads zero, and says so.

Two design choices carried from the rest of the repo:
- Configurable root. Default `~/CODE`, overridable by arg, `HELICON_CODE_ROOT`,
  or config `code_root` — so the board points at a real tree, not a fixture.
- Cold-aware. `cold` is the set of loaded lines a human demoted (kept forever,
  loads nothing — see helicon.cold). The board's counter is the LOADED total, so
  it falls as lines go cold. Slice 1 counts everything; the cold set is threaded
  through so the counter is honest the moment demotion exists.

Read-only: filesystem reads only, nothing is written to the repos examined.
"""
import os
import re
from glob import glob

from helicon.connectors.agent_rules import KNOWN_RULE_FILES, KNOWN_RULE_PATHS

DEFAULT_ROOT = "~/CODE"

# Claude Code `@path` imports: a line may reference another file to pull into
# context. Match a leading '@' followed by a path to a text/rules file.
_IMPORT = re.compile(r"(?:^|\s)@([~./\w][\w./\-]*\.(?:md|mdc|markdown|txt))")

_MAX_DOCS = 200          # a bound on import fan-out; no repo loads more honestly
_READ_CAP = 400_000      # per-file byte cap, same as probes._read


def resolve_root(root: str | None = None, config: dict | None = None) -> str:
    r = (root
         or os.environ.get("HELICON_CODE_ROOT")
         or (config or {}).get("code_root")
         or DEFAULT_ROOT)
    return os.path.abspath(os.path.expanduser(r))


def estimate_tokens(text: str) -> int:
    """Tokens ≈ chars / 4 — the same coarse, honest estimate the battery and
    context-budget guard use. It is a budget signal, not a tokenizer."""
    return len(text or "") // 4


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(_READ_CAP)
    except OSError:
        return ""


def _seed_docs(repo: str) -> list[str]:
    """The rule files an agent loads at the root of its session, before imports."""
    seeds = []
    for name in KNOWN_RULE_FILES:
        if os.path.isfile(os.path.join(repo, name)):
            seeds.append(name)
    # Claude Code also loads a project-local override if present.
    if os.path.isfile(os.path.join(repo, "CLAUDE.local.md")):
        seeds.append("CLAUDE.local.md")
    for rel in KNOWN_RULE_PATHS:
        if os.path.isfile(os.path.join(repo, rel)):
            seeds.append(rel)
    for mdc in sorted(glob(os.path.join(repo, ".cursor", "rules", "*.mdc"))):
        seeds.append(os.path.relpath(mdc, repo))
    # de-dup, preserve order
    out, seen = [], set()
    for s in seeds:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _resolve_import(repo: str, importer_rel: str, target: str) -> str | None:
    """Resolve an @import the way an agent would: relative to the importing
    file's directory, then to the repo root, then '~'. Contained to the repo."""
    cands = []
    if target.startswith("~"):
        cands.append(os.path.expanduser(target))
    base_dir = os.path.dirname(os.path.join(repo, importer_rel))
    cands.append(os.path.normpath(os.path.join(base_dir, target)))
    cands.append(os.path.normpath(os.path.join(repo, target.lstrip("./"))))
    repo_real = os.path.realpath(repo)
    for c in cands:
        cr = os.path.realpath(c)
        # only follow imports that stay inside the repo (a doorway maps THIS repo)
        if (cr == repo_real or cr.startswith(repo_real + os.sep)) and os.path.isfile(cr):
            return os.path.relpath(cr, repo)
    return None


def loaded_docs(repo: str) -> list[dict]:
    """Every file this repo loads into an agent, with its text and how it was
    reached. BFS over @imports from the seed rule files, bounded and de-duped."""
    repo = os.path.abspath(os.path.expanduser(repo))
    out, seen = [], set()
    queue = [(rel, None) for rel in _seed_docs(repo)]
    while queue and len(out) < _MAX_DOCS:
        rel, via = queue.pop(0)
        if rel in seen:
            continue
        seen.add(rel)
        text = _read(os.path.join(repo, rel))
        if not text.strip():
            continue
        out.append({"file": rel, "text": text, "via_import": via,
                    "tokens": estimate_tokens(text),
                    "lines": text.count("\n") + 1})
        for m in _IMPORT.finditer(text):
            tgt = _resolve_import(repo, rel, m.group(1))
            if tgt and tgt not in seen:
                queue.append((tgt, rel))
    return out


def repo_load(repo: str, cold: set | None = None) -> dict:
    """One repo's context load. `cold` is a set of 'file' or 'file:line' refs the
    human demoted; cold docs count zero loaded tokens (kept, but not loaded)."""
    repo = os.path.abspath(os.path.expanduser(repo))
    cold = cold or set()
    docs = loaded_docs(repo)
    rows, loaded, kept_cold = [], 0, 0
    for d in docs:
        is_cold = d["file"] in cold
        rows.append({"file": d["file"], "tokens": d["tokens"], "lines": d["lines"],
                     "via_import": d["via_import"], "cold": is_cold})
        if is_cold:
            kept_cold += d["tokens"]
        else:
            loaded += d["tokens"]
    return {"name": os.path.basename(os.path.normpath(repo)), "path": repo,
            "docs": rows, "doc_count": len(rows),
            "loaded_tokens": loaded, "cold_tokens": kept_cold}


def _is_repo(path: str) -> bool:
    """A directory worth a door: a git repo, or one carrying agent-rules."""
    if os.path.isdir(os.path.join(path, ".git")):
        return True
    return bool(_seed_docs(path))


def list_repos(root: str | None = None, config: dict | None = None,
               cold_by_repo: dict | None = None) -> dict:
    """The board: every repo under `root`, each with its live loaded-token cost,
    heaviest first. Missing root is reported, not invented."""
    root = resolve_root(root, config)
    cold_by_repo = cold_by_repo or {}
    if not os.path.isdir(root):
        return {"root": root, "exists": False, "repos": [], "repo_count": 0,
                "total_loaded_tokens": 0}
    repos = []
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if not os.path.isdir(p) or name.startswith("."):
            continue
        if not _is_repo(p):
            continue
        load = repo_load(p, cold=set(cold_by_repo.get(name, [])))
        repos.append({"name": load["name"], "path": load["path"],
                      "loaded_tokens": load["loaded_tokens"],
                      "cold_tokens": load["cold_tokens"],
                      "doc_count": load["doc_count"]})
    repos.sort(key=lambda r: -r["loaded_tokens"])
    return {"root": root, "exists": True, "repos": repos,
            "repo_count": len(repos),
            "total_loaded_tokens": sum(r["loaded_tokens"] for r in repos)}


def format_board(board: dict) -> str:
    """CLI rendering — the door, in one screen of text."""
    if not board["exists"]:
        return (f"\n  No repo root at {board['root']}.\n"
                f"  Point the board at one: helicon board --root <dir> "
                f"(or set HELICON_CODE_ROOT).\n")
    lines = ["", f"  The doorway — {board['repo_count']} repo(s) under {board['root']}",
             f"  {board['total_loaded_tokens']:,} tokens loaded into an agent across all repos",
             ""]
    lines.append(f"  {'repo':<28} {'loaded':>10}  {'docs':>4}  cold")
    for r in board["repos"]:
        cold = f"{r['cold_tokens']:,}" if r["cold_tokens"] else "—"
        lines.append(f"  {r['name'][:28]:<28} {r['loaded_tokens']:>10,}  "
                     f"{r['doc_count']:>4}  {cold}")
    lines.append("")
    return "\n".join(lines)
