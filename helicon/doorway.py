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
import difflib
import json
import os
import re
import sqlite3
import sys
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


def _by_line(results: list) -> dict:
    """(file, line) -> the verdict that line deserves.

    One doc line can carry several probeable claims, so several probe results
    can land on it. A plain `{(f, l): r for r in results}` keeps whichever ran
    LAST, and that silently erased real contradictions: world-relay's
    CLAUDE.md:35 probes CONTRADICTED then UPHELD, and the board reported it
    upheld. The failure is in the one direction that matters — a claim the code
    disproves rendered as fine — so precedence is explicit and disproof wins.
    An executed disproof is not cancelled by a different claim on the same line
    happening to pass.
    """
    from helicon import probes
    rank = {probes.CONTRADICTED: 2, probes.UNVERIFIABLE: 1, probes.UPHELD: 0}
    out = {}
    for r in results:
        if not r.get("line"):
            continue
        key = (r["file"], r["line"])
        cur = out.get(key)
        if cur is None or rank.get(r["verdict"], 0) > rank.get(cur["verdict"], 0):
            out[key] = r
    return out


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
    by_line = _by_line(results)
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
                "moot": bool((pv or {}).get("moot")),
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


# --------------------------------------------------------------------------
# the doorway as a GATE — the board decides, this stops a live session
# --------------------------------------------------------------------------
#
# Everything above answers "what does this repo load, and is it true?". That is
# analysis: it lands in a CLI a human has to remember to type. This half turns
# the same verdicts into an act — a real Claude Code UserPromptSubmit hook that
# refuses to let a run start against a repo whose loaded docs the running code
# DISPROVES.
#
# Three rules it obeys, all from the product law:
#
# 1. Machine-applied. A CONTRADICTED verdict came from a probe that executed and
#    disagreed. Nothing about that needs a human, so no human is asked.
# 2. Cold lines never block. Demoting a line is the sanctioned fix: it is kept
#    forever and loads nothing, so it cannot poison a run and must not stop one.
#    That makes `helicon board --repo X --demote` a real exit from the block,
#    not a suggestion.
# 3. Fail open, loudly. Any error in here lets the prompt through. A gate that
#    bricks the terminal when it crashes would be removed within a day, and then
#    it governs nothing. The `allowed` / `blocked` events are what distinguish a
#    clean repo from a broken hook — absence of a block proves neither.

# What a human types to proceed anyway. Chosen because it needs no flag, no
# second terminal, and no context switch: you are already at a prompt, so you
# retype the prompt with the reason on the front, and the reason is logged
# verbatim. An override with no stated reason is not an override.
OVERRIDE_PREFIX = "helicon-override:"

_GATE_CACHE_TTL_UNUSED = None  # (no TTL: the fingerprint is the only staleness test)


def ensure_gate_table(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS doorway_gate_cache (
        repo_path   TEXT PRIMARY KEY,
        fingerprint TEXT NOT NULL,   -- git HEAD + every loaded doc's size/mtime + cold set
        payload     TEXT NOT NULL,   -- json: the CONTRADICTED lines at that fingerprint
        checked_at  TEXT NOT NULL
    )""")
    conn.commit()


def _git_head(repo: str) -> str:
    from helicon import probes
    code, out = probes._run(["git", "rev-parse", "HEAD"], repo, timeout=5)
    return out.strip() if code == 0 else ""


def fingerprint(conn, repo: str) -> str:
    """What must change before a cached verdict is worth re-earning: the commit,
    every loaded doc's size+mtime, and the cold set. Any of the three moving
    means the probe result may no longer hold, so it is re-run. A cache that
    could serve a verdict the repo has already outgrown would be exactly the
    stale-memory failure this whole product exists to catch."""
    repo = os.path.abspath(os.path.expanduser(repo))
    parts = [_git_head(repo)]
    for d in _seed_docs(repo) or []:
        p = os.path.join(repo, d)
        try:
            st = os.stat(p)
            parts.append(f"{d}:{st.st_size}:{st.st_mtime_ns}")
        except OSError:
            parts.append(f"{d}:missing")
    name = os.path.basename(os.path.normpath(repo))
    parts.append("cold=" + ",".join(sorted(cold_refs(conn, name))))
    # The PROBER is the fourth thing that can change the answer, and it was
    # missing. A false positive fixed in probes.py kept being served from cache
    # against an untouched repo — the code that decides was the one input the
    # staleness test did not watch, which is precisely the bug class this
    # product sells. Its size+mtime is enough: any edit moves it.
    try:
        from helicon import probes as _p
        st = os.stat(_p.__file__)
        parts.append(f"prober:{st.st_size}:{st.st_mtime_ns}")
    except OSError:
        parts.append("prober:unknown")
    import hashlib
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def contradicted_lines(conn, repo: str, config: dict | None = None,
                       allow_network: bool = False) -> list[dict]:
    """The loaded, NOT-cold lines the running code disproves. Cold lines are
    excluded on purpose (rule 2 above): they load nothing, so they cannot be the
    reason a run is refused.

    MOOT lines are excluded too, and for the stricter reason: they are not
    disproved at all. A rule the code has made unreachable still agrees with the
    code. The board reports them; the gate must not spend its one interruption
    on them."""
    detail = repo_detail(conn, repo, config, allow_network)
    from helicon import probes
    out = []
    for doc in detail["docs"]:
        if doc["cold"]:
            continue
        for ln in doc["lines"]:
            if (ln["verdict"] == probes.CONTRADICTED and not ln["cold"]
                    and not ln.get("moot")):
                out.append({"file": doc["file"], "line": ln["line"],
                            "ref": ln["ref"], "text": ln["text"],
                            "probe": ln.get("probe"), "output": ln.get("output"),
                            "why": ln.get("why")})
    return out


def verdict(conn, repo: str, config: dict | None = None,
            allow_network: bool = False, fresh: bool = False) -> dict:
    """A repo's gate verdict, cached on the fingerprint. Cold ≈1s (the probes
    execute); warm ≈0ms. `fresh=True` forces the probes to run again."""
    import json as _json
    repo = os.path.abspath(os.path.expanduser(repo))
    fp = fingerprint(conn, repo)
    ensure_gate_table(conn)
    if not fresh:
        row = conn.execute(
            "SELECT payload, checked_at FROM doorway_gate_cache "
            "WHERE repo_path = ? AND fingerprint = ?", (repo, fp)).fetchone()
        if row:
            return {"repo": os.path.basename(os.path.normpath(repo)),
                    "path": repo, "fingerprint": fp, "cached": True,
                    "checked_at": row["checked_at"],
                    "contradicted": _json.loads(row["payload"])}
    lines = contradicted_lines(conn, repo, config, allow_network)
    now = _now()
    conn.execute(
        "INSERT OR REPLACE INTO doorway_gate_cache "
        "(repo_path, fingerprint, payload, checked_at) VALUES (?,?,?,?)",
        (repo, fp, _json.dumps(lines), now))
    conn.commit()
    return {"repo": os.path.basename(os.path.normpath(repo)), "path": repo,
            "fingerprint": fp, "cached": False, "checked_at": now,
            "contradicted": lines}


def parse_override(prompt: str) -> str | None:
    """The reason, if this prompt is an override. Returns None when it is an
    ordinary prompt, and None when the prefix is present but carries no reason —
    'helicon-override:' alone is not an override, it is an empty gesture."""
    p = (prompt or "").lstrip()
    if p[:len(OVERRIDE_PREFIX)].lower() != OVERRIDE_PREFIX:
        return None
    reason = p[len(OVERRIDE_PREFIX):].strip()
    return reason or None


def decide(v: dict, prompt: str = "") -> dict:
    """block / allow / override, from a verdict and the prompt that arrived."""
    bad = v.get("contradicted") or []
    if not bad:
        return {"action": "allow", "reason": "", "contradicted": []}
    reason = parse_override(prompt)
    if reason:
        return {"action": "override", "reason": reason, "contradicted": bad}
    return {"action": "block", "reason": "", "contradicted": bad}


def format_block(v: dict, decision: dict, mode: str = "block") -> str:
    """The banner a human reads in their own terminal. It names the exact lines,
    the ways out, and nothing else.

    `mode` changes what the banner is claiming happened, and lying about that is
    worse than saying nothing: in warn mode the run IS starting, so a banner
    that says "refused" teaches the operator to distrust every future banner.
    """
    bad = decision["contradicted"]
    head = v["fingerprint"][:7]
    if mode == "warn":
        out = ["⚠ HELICON — running anyway, but your loaded context is wrong.", "",
               f"  repo: {v['repo']} @ {head}",
               f"  {len(bad)} loaded claim(s) the running code DISPROVES "
               f"(the agent has been told):", ""]
    else:
        out = ["⛔ HELICON — this run has not earned the right to start.", "",
               f"  repo: {v['repo']} @ {head}",
               f"  {len(bad)} loaded claim(s) the running code DISPROVES:", ""]
    for b in bad:
        where = f"{b['file']}:{b['line']}" if b.get("line") else b["file"]
        out.append(f"  {where}")
        out.append(f"    claim  {b['text'][:100]}")
        if b.get("probe"):
            out.append(f"    probe $ {b['probe']}")
        if b.get("output"):
            out.append(f"    stdout  {str(b['output']).splitlines()[0][:88]}")
        out.append("")
    first = bad[0]
    ref = first.get("ref") or f"{first['file']}#{first.get('line','')}"
    out += [f"  fix:      helicon board --repo {v['repo']} --demote {ref}",
            "            (or correct the line — the gate re-probes on the next prompt)"]
    if mode != "warn":
        # Only offered when it is needed. In warn mode the prompt already ran,
        # so telling the operator to retype it with a prefix is busywork.
        out += [f"  override: retype your prompt starting with",
                f"            {OVERRIDE_PREFIX} <why this may run anyway>",
                f"  stop blocking: HELICON_GATE_MODE=warn (or doorway.gate_mode "
                f"in config.json)"]
    out.append("")
    return "\n".join(out)


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


# --------------------------------------------------------------------------
# The stranger's install — the doorway gate as a Claude Code hook.
#
# LANE 2: make the doorway installable by someone who is not the author, on a
# machine that is not this checkout, in one command. The gate itself is keyless
# and config-free (capture.hook_gate -> doorway.verdict, deterministic git
# probes), so a stranger needs no config.json and no seeded store — only a place
# to keep the gate's own log. Writing to ~/.claude/settings.json is the single
# most dangerous thing in this repo, so every write below is backed up, shown as
# a diff, confirmed, idempotent, and exactly reversible. The pure functions here
# (load/add/remove/diff) take and return dicts so the writer is fully testable
# without touching a real settings file.
# --------------------------------------------------------------------------

DOORWAY_MARKER = "helicon doorway gate"   # identifies the hook Helicon added


def user_home() -> str:
    """Where the gate keeps its own store — independent of any checkout or
    config.json, so the gate runs for a stranger who only `pip install`ed."""
    return os.environ.get("HELICON_HOME") or os.path.expanduser("~/.helicon")


def user_db_path() -> str:
    return os.path.join(user_home(), "doorway.db")


def gate_db_path() -> str:
    """Where the gate logs. A configured user's blocks belong in the SAME store
    their dashboard and `helicon runs` read — otherwise a block on their desktop
    lands in a side-store nothing surfaces (the "I gated a run and can't see it"
    trap). A stranger with no config keeps the config-free ~/.helicon store, and
    an explicit HELICON_HOME always forces the standalone store."""
    if os.environ.get("HELICON_HOME"):
        return user_db_path()
    try:
        from helicon.config import load_config
        cfg = load_config()
        if cfg and cfg.get("db_path"):
            return cfg["db_path"]
    except Exception:
        pass
    return user_db_path()


def claude_settings_path() -> str:
    return os.environ.get("CLAUDE_SETTINGS") or \
        os.path.expanduser("~/.claude/settings.json")


def gate_command() -> str:
    """The command the hook runs, pinned to THIS interpreter — the one that has
    helicon importable. The author's original wrapper existed only because a
    bare `helicon` on PATH raised ModuleNotFoundError from outside a checkout;
    pinning the interpreter is the real packaging fix, and it needs no wrapper."""
    return f"{sys.executable} -m helicon doorway gate"


def _hook_group(cmd: str) -> dict:
    return {"hooks": [{"type": "command", "command": cmd}]}


def load_settings(path: str) -> dict:
    """Parse settings.json, or {} when absent/empty. A malformed file raises
    (json.JSONDecodeError, a ValueError) — we must never silently overwrite a
    file we could not read."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if not text.strip():
        return {}
    return json.loads(text)


def _groups(settings: dict) -> list:
    return (settings.get("hooks") or {}).get("UserPromptSubmit") or []


def has_doorway_hook(settings: dict) -> bool:
    return any(DOORWAY_MARKER in (h.get("command") or "")
               for g in _groups(settings) for h in (g.get("hooks") or []))


def add_doorway_hook(settings: dict, cmd: str) -> dict:
    """Settings with our UserPromptSubmit group added — idempotent, and without
    disturbing any hook already there."""
    import copy
    new = copy.deepcopy(settings)
    if has_doorway_hook(new):
        return new
    new.setdefault("hooks", {}).setdefault("UserPromptSubmit", []).append(
        _hook_group(cmd))
    return new


def remove_doorway_hook(settings: dict) -> dict:
    """Settings with EXACTLY our groups removed — every other hook and every
    other key left as it was. Empty containers we would have created are pruned;
    a UserPromptSubmit list still holding other hooks is kept."""
    import copy
    new = copy.deepcopy(settings)
    hooks = new.get("hooks")
    if not isinstance(hooks, dict):
        return new
    ups = hooks.get("UserPromptSubmit")
    if not isinstance(ups, list):
        return new
    kept = [g for g in ups
            if not any(DOORWAY_MARKER in (h.get("command") or "")
                       for h in (g.get("hooks") or []))]
    if kept:
        hooks["UserPromptSubmit"] = kept
    else:
        hooks.pop("UserPromptSubmit", None)
        if not hooks:
            new.pop("hooks", None)
    return new


def settings_diff(old: dict, new: dict, path: str) -> str:
    a = json.dumps(old, indent=2, sort_keys=True).splitlines(keepends=True)
    b = json.dumps(new, indent=2, sort_keys=True).splitlines(keepends=True)
    label = os.path.basename(path)
    return "".join(difflib.unified_diff(a, b, fromfile=f"{label} (now)",
                                        tofile=f"{label} (after)"))


def backup_settings(path: str) -> str | None:
    """Copy the current file aside before any write. Returns the backup path, or
    None when there was nothing to back up (first-ever write)."""
    if not os.path.exists(path):
        return None
    import shutil
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = f"{path}.helicon-bak.{ts}"
    shutil.copy2(path, bak)
    return bak


def write_settings(path: str, settings: dict) -> None:
    """Atomic write (temp + rename) so an interrupted write cannot truncate the
    user's settings."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.helicon-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(settings, indent=2) + "\n")
    os.replace(tmp, path)


def last_fired(db_path: str | None = None) -> dict | None:
    """The most recent time the gate blocked or was overridden, from its own
    store. None when the store does not exist or nothing has fired yet."""
    db_path = db_path or gate_db_path()
    if not os.path.exists(db_path):
        return None
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT kind, ts FROM run_events "
            "WHERE kind IN ('gate_blocked','gate_override') "
            "ORDER BY ts DESC LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    return {"kind": row[0], "ts": row[1]} if row else None
