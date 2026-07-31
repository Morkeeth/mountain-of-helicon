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
import sqlite3
from datetime import datetime, timezone
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
               conn=None) -> dict:
    """The board: every repo under `root`, each with its live loaded-token cost,
    heaviest first. When a store `conn` is given, tokens demoted to cold are
    subtracted — so the board counter falls as a human works. Missing root is
    reported, not invented."""
    root = resolve_root(root, config)
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
        load = repo_load(p)
        cold = cold_refs(conn, name) if conn is not None else {}
        cold_tokens = sum(cold.values())
        loaded = max(0, load["loaded_tokens"] - cold_tokens)
        repos.append({"name": load["name"], "path": load["path"],
                      "loaded_tokens": loaded, "cold_tokens": cold_tokens,
                      "doc_count": load["doc_count"]})
    repos.sort(key=lambda r: -r["loaded_tokens"])
    return {"root": root, "exists": True, "repos": repos,
            "repo_count": len(repos),
            "total_loaded_tokens": sum(r["loaded_tokens"] for r in repos)}


# --------------------------------------------------------------------------
# cold storage — a demoted line is KEPT forever and loads nothing
# --------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def ensure_cold_table(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS doorway_cold (
        repo TEXT NOT NULL,
        ref TEXT NOT NULL,          -- 'file' (whole doc) or 'file#line' (one line)
        tokens INTEGER DEFAULT 0,   -- the exact weight removed from the loaded set
        reason TEXT,
        decided_at TEXT NOT NULL,
        PRIMARY KEY (repo, ref)
    )""")
    conn.commit()


def cold_refs(conn, repo: str) -> dict:
    """ref -> tokens for everything demoted to cold in this repo. Cold keeps the
    line (it is still in the store and on the board), it just loads nothing."""
    if conn is None:
        return {}
    try:
        ensure_cold_table(conn)
        return {r["ref"]: (r["tokens"] or 0) for r in conn.execute(
            "SELECT ref, tokens FROM doorway_cold WHERE repo = ?", (repo,))}
    except sqlite3.Error:
        return {}


def demote(conn, repo: str, ref: str, tokens: int = 0, reason: str = "") -> dict:
    """Move one line (or a whole doc) to cold: kept forever, loads nothing. The
    token weight is recorded so the board counter falls by exactly this much."""
    ensure_cold_table(conn)
    conn.execute(
        "INSERT OR REPLACE INTO doorway_cold (repo, ref, tokens, reason, decided_at) "
        "VALUES (?,?,?,?,?)", (repo, ref, int(tokens or 0), reason, _now()))
    conn.commit()
    return {"ok": True, "repo": repo, "ref": ref, "tokens": int(tokens or 0),
            "reason": reason}


def promote(conn, repo: str, ref: str) -> dict:
    """Bring a cold line back into the loaded set (undo a demotion)."""
    ensure_cold_table(conn)
    cur = conn.execute("DELETE FROM doorway_cold WHERE repo = ? AND ref = ?",
                       (repo, ref))
    conn.commit()
    return {"ok": True, "repo": repo, "ref": ref, "restored": cur.rowcount}


# --------------------------------------------------------------------------
# repo detail — every loaded line, its verdict, its cold state
# --------------------------------------------------------------------------

def _same_sentence(a: str, b: str) -> bool:
    na = re.sub(r"\s+", " ", re.sub(r"[*`]", "", a or ""))[:48].strip()
    nb = re.sub(r"\s+", " ", re.sub(r"[*`]", "", b or ""))[:48].strip()
    return bool(na) and na == nb


def repo_detail(conn, repo_path: str, config: dict | None = None,
                allow_network: bool = False) -> dict:
    """Every loaded line of a repo's context, each carrying a probe verdict:
    UPHELD / CONTRADICTED / UNVERIFIABLE. A line with no probe is UNVERIFIABLE —
    a verdict, not a gap. Cold lines are shown (kept) but marked loads-nothing.
    """
    from helicon import probes
    repo = os.path.abspath(os.path.expanduser(repo_path))
    name = os.path.basename(os.path.normpath(repo))
    docs = loaded_docs(repo)
    try:
        results = probes.probe_docs(conn, repo, config, allow_network)
    except Exception:
        results = []
    by_line = {(r["file"], r["line"]): r for r in results if r.get("line")}
    cold = cold_refs(conn, name)

    doc_out, loaded_total = [], 0
    counts = {probes.UPHELD: 0, probes.CONTRADICTED: 0, probes.UNVERIFIABLE: 0}
    for d in docs:
        file, text = d["file"], d["text"]
        doc_cold = file in cold
        lines = []
        for a in probes.split_assertions(text):
            ln = probes._line_of(text, a["text"])
            ref = f"{file}#{ln}" if ln else f"{file}#p{abs(hash(a['text'])) % 100000}"
            pv = by_line.get((file, ln))
            if pv is None:
                pv = next((r for r in results
                           if r["file"] == file and _same_sentence(r["sentence"], a["text"])), None)
            verdict = pv["verdict"] if pv else probes.UNVERIFIABLE
            toks = estimate_tokens(a["text"])
            is_cold = doc_cold or ref in cold
            counts[verdict] = counts.get(verdict, 0) + 1
            lines.append({
                "ref": ref, "line": ln, "tokens": toks, "cold": is_cold,
                "text": re.sub(r"\s+", " ", a["text"])[:220],
                "verdict": verdict, "kind": (pv or {}).get("kind"),
                "why": (pv or {}).get("why") or
                       ("no probe exists for this claim — unverifiable by "
                        "construction, not a gap" if not pv else ""),
                "probe": (pv or {}).get("probe"), "output": (pv or {}).get("output"),
            })
        cold_here = sum(l["tokens"] for l in lines if l["cold"])
        doc_loaded = 0 if doc_cold else max(0, d["tokens"] - cold_here)
        loaded_total += doc_loaded
        doc_out.append({"file": file, "tokens": d["tokens"],
                        "loaded_tokens": doc_loaded, "cold": doc_cold,
                        "via_import": d["via_import"], "lines": lines})

    return {"repo": name, "path": repo, "docs": doc_out,
            "loaded_tokens": loaded_total, "doc_count": len(doc_out),
            "verdict_counts": counts,
            "contradicted": counts[probes.CONTRADICTED],
            "cold_tokens": sum(cold.values())}


def format_detail(detail: dict) -> str:
    """CLI rendering of one repo's loaded lines and their verdicts."""
    from helicon import probes
    c = detail["verdict_counts"]
    mark = {probes.CONTRADICTED: "CONTRADICTED", probes.UPHELD: "UPHELD",
            probes.UNVERIFIABLE: "UNVERIFIABLE"}
    lines = ["", f"  {detail['repo']} — {detail['loaded_tokens']:,} tokens loaded",
             f"  {c.get(probes.CONTRADICTED, 0)} contradicted · "
             f"{c.get(probes.UNVERIFIABLE, 0)} unverifiable · "
             f"{c.get(probes.UPHELD, 0)} upheld", ""]
    for doc in detail["docs"]:
        tag = " (cold — loads nothing)" if doc["cold"] else ""
        lines.append(f"  {doc['file']}  [{doc['loaded_tokens']:,} tok]{tag}")
        for ln in doc["lines"]:
            m = mark.get(ln["verdict"], ln["verdict"])
            cold = " ·cold" if ln["cold"] else ""
            lines.append(f"     {m:<13} {ln['text'][:90]}{cold}")
            if ln["verdict"] == probes.CONTRADICTED and ln.get("probe"):
                lines.append(f"        probe $ {ln['probe']}")
                if ln.get("output"):
                    lines.append(f"        stdout  {str(ln['output']).splitlines()[0][:80]}")
        lines.append("")
    return "\n".join(lines)


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
