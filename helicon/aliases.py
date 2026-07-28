"""Supersession aliases — the R4 check.

An entity gets renamed; the old name lives on across memory. The public
record says this is where memory stores collapse (accuracy on superseded
facts drops 68% -> 28% as history grows — see ROT.md R4), and it happened
here: a project rename left 710+ live memory items referencing the dead name.

The alias table records the rename as a fact the store can reason with:
old_name -> new_name at renamed_at. Every dead-name reference in live memory
then triages deterministically, by written rule, not vibes:

  history        created before the rename. It was true when written;
                 retiring it would be R7 (wrong eviction). Left alone.
  rename-aware   created after the rename, mentions BOTH names — it is
                 *about* the rename (commits, decision logs). Fine.
  current-claim  created after the rename, mentions ONLY the dead name.
                 Memory written in the present tense of a name that no
                 longer exists. This is the rot.

Plus the serving-side check: retrieve top-K for the *new* name the way an
agent would; every hit that speaks only the dead name is a superseded fact
being served as current context.

One audit finding per alias (audit_type='supersession'), idempotent, counts
in the finding — never one row per cube (700 rows of backlog is its own rot).
"""
import json
import os
import re
import sqlite3
import subprocess
from datetime import datetime, timezone

from helicon.models import AuditResult
from helicon.db import insert_audit

# --- the code arm: a dead name in prose is rot; in a code path it is an outage
#
# A dead name you can read past is prose. A dead name a lookup executes is an
# outage. R4 reported 341 RELAY current-claims as a COUNT, with no way to tell
# which of them a code path was executing. That distinction is worth drawing.
#
# CORRECTION 2026-07-15: this arm was built on a MISATTRIBUTED exemplar and the
# error is worth keeping visible. The story was "agent:relay -> getAgent('relay')
# -> no such key -> null, silently, for 13 days". The blackout is real, the cause
# is not: `relay` was NEVER a key in AGENT_REGISTRY in any of the 15 commits that
# ever touched agents.ts, 12 of the 41 broken tasks predate the rename, and
# getAgent("favour") returns null too because `favour` is not a key either. The
# real cause is a namespace collision (agent: means both "the platform seeded
# this" and "a registry agent posted this"), fixed in world-relay ea2548c.
#
# The sharp part, and the reason this comment stays: the "fix" the old story
# implies — update the dead name — REPRODUCES the outage under a live name, and
# this check would then report CLEAN on a live outage. A dead name is a weak
# proxy for a dangling reference. The honest check is "this key resolves to
# nothing", which needs the registry, not a rename table. Until that exists, this
# arm reports leads and claims no incident.
#
# How the error happened is the more useful finding: the FAVOUR lane hedged
# ("agent:relay is ALSO a dead name, which is LIKELY how it rotted unnoticed"),
# the hedge was promoted to a headline in a summary, and I built on the headline
# without checking the premise. One `git log` on agents.ts would have caught it.
#
# This arm reports LEADS, not verdicts, and its precision limit is the point.
# "relay" and "glaze" are English words. Walking the tree found 61 hits in
# world-relay, nearly all noise: .vercel build output and OpenZeppelin's
# vendored governance relay(). `git ls-files` is the honest primitive — it is
# what the repo actually authors and commits, which cut 879 files to 149 and
# took build output and node_modules with it. The name must also appear as a
# COMPLETE quoted token (an identifier or key), never a word inside prose, or
# "Try RELAY Favours and tell us what you think" scores as a code reference.
#
# Tests are counted separately rather than filtered. Once the outage was fixed,
# world-relay's `agent:relay` cases became the deliberate legacy contract, and
# flagging those would make R4 cry wolf about code that is correct. A check that
# cries wolf discredits the exam it belongs to.
_CODE_EXT = (".ts", ".tsx", ".js", ".jsx", ".py", ".json", ".yml", ".yaml",
             ".sh", ".toml", ".env")
_VENDOR = ("/lib/", "/vendor/", "/third_party/", "/node_modules/", ".min.")
_TEST_HINT = ("__tests__", "/test/", "/tests/", ".test.", ".spec.", "_test.")
# a line whose first non-space character opens a comment or a docstring
_COMMENT_RX = re.compile(r'\s*(#|//|/\*|\*|"""|\'\'\')')


def _code_rx(name: str):
    """The dead name as a whole quoted token ("relay") or namespaced inside one
    ("agent:relay") — never a word inside a sentence."""
    n = re.escape(name)
    return re.compile(
        "([\"'`])\\s*" + n + "\\s*\\1" + "|" + "[\"'`][a-z_-]*:" + n + "[\"'`]",
        re.I)


def _is_self(repo: str, skip_roots: list[str]) -> bool:
    """True if `repo` IS this checkout, or contains it (a worktree under it)."""
    r = os.path.realpath(repo)
    return any(s == r or s.startswith(r + os.sep) for s in skip_roots)


def _self_repo_root() -> str:
    """The checkout this code is running from — realpath'd."""
    return os.path.realpath(os.path.dirname(os.path.dirname(__file__)))


def repos_dir_from_config(config: dict | None) -> str | None:
    """Where the code arm is allowed to look, declared in config or nowhere.

    CORRECTION 2026-07-28: this used to default to the literal string "~/CODE",
    so BOTH the production R4 check and every unit test that touched it walked
    the developer's home directory — 37 repos, a `git ls-files` each. Proven two
    ways: `HOME=<empty tmp> pytest tests/test_watch.py::test_alias_drift_flips_r4`
    passed in 0.53s while the same test on the real HOME failed in 6.25s, because
    the ~/CODE scan had already put R4 in ROT FOUND before the test's dead-name
    cube was inserted, so no FLIP was ever emitted. An exam whose verdict depends
    on the examiner's home directory is not an exam.

    There is no implicit default now. Unconfigured means the arm does not run and
    says so (`scanned: False`) — an unmeasured arm must never read as clean.
    """
    if not config:
        return None
    explicit = (config.get("aliases") or {}).get("repos_dir")
    if not explicit:
        explicit = ((config.get("connectors") or {}).get("git") or {}).get("repos_dir")
    return os.path.expanduser(explicit) if explicit else None


def code_refs(old_name: str, new_name: str = "", repos_dir: str | None = None,
              cap: int = 60, exclude_self: bool = True) -> dict:
    """Where the dead name is EXECUTABLE, not merely written.

    `repos_dir=None` means "not configured": no scan, `scanned: False`. Callers
    resolve it from config via repos_dir_from_config(); nothing walks a home
    directory by default.
    """
    if not repos_dir:
        return {"leads": [], "legacy_tests": 0, "repos": 0, "scanned": False,
                "repos_dir": None}
    root = os.path.expanduser(repos_dir)
    # The tool's own source is excluded from its own scan. helicon/cockpit.py
    # line 26 is a SAFE_TERMINALS allowlist reading ["x-engine", "glaze",
    # "favour"] — a quoted dead-name token in executable code, so the check
    # scored it as a lead and `data/watch-state.json` sat at "R4: ROT FOUND"
    # permanently: the rename detector flagging itself, unable to reach CLEAN
    # by construction. A rename table is allowed to contain the dead name; that
    # is what a rename table IS. Scanning yourself is not evidence about the
    # world.
    skip_roots = [_self_repo_root()] if exclude_self else []
    rx = _code_rx(old_name)
    # Same rule the prose triage already uses: a line naming BOTH the old and
    # the new name is rename-AWARE (a migration, an alias declaration). It is
    # about the rename, so it is not a dead reference.
    #
    # The new name must be a quoted TOKEN, exactly like the old one. Matching it
    # as a bare word was asymmetric and it silently dropped a real outage: in
    # seed/route.ts, lines 11, 12 and 13 all carry agentId:"relay", and line 12
    # alone was suppressed because its product copy reads "What favour would you
    # ask someone nearby" — prose, inside a string, matching \bfavour\b. Lines 11
    # and 13 survived by luck ("Favours" and "favourite" do not match \b). In a
    # codebase whose entire domain vocabulary is the new name, a bare-word rule
    # makes every dead reference near product copy invisible.
    new_rx = _code_rx(new_name) if new_name else None
    leads, legacy, repos, skipped_self = [], 0, 0, []
    if not os.path.isdir(root):
        return {"leads": [], "legacy_tests": 0, "repos": 0, "scanned": False,
                "repos_dir": root}
    for entry in sorted(os.listdir(root)):
        repo = os.path.join(root, entry)
        if not os.path.isdir(os.path.join(repo, ".git")):
            continue
        if _is_self(repo, skip_roots):
            skipped_self.append(entry)
            continue
        try:
            tracked = subprocess.run(["git", "ls-files"], cwd=repo, timeout=20,
                                     capture_output=True,
                                     text=True).stdout.splitlines()
        except (OSError, subprocess.SubprocessError):
            continue
        repos += 1
        for rel in tracked:
            if not rel.endswith(_CODE_EXT) or any(v in "/" + rel for v in _VENDOR):
                continue
            try:
                with open(os.path.join(repo, rel), encoding="utf-8",
                          errors="replace") as f:
                    lines = f.read().splitlines()
            except OSError:
                continue
            is_test = any(t in "/" + rel for t in _TEST_HINT)
            for i, line in enumerate(lines, 1):
                if not rx.search(line):
                    continue
                # A dead name in a COMMENT is prose that happens to live in a
                # source file — it executes nothing. Caught immediately by this
                # function flagging its own explanatory comments, which is the
                # cleanest possible proof of the distinction it is drawing.
                if _COMMENT_RX.match(line):
                    continue
                if new_rx and new_rx.search(line):
                    continue  # rename-aware: names both sides
                if is_test:
                    legacy += 1
                elif len(leads) < cap:
                    leads.append({"repo": entry, "file": rel, "line": i,
                                  "text": line.strip()[:120]})
    return {"leads": leads, "legacy_tests": legacy, "repos": repos,
            "scanned": True, "repos_dir": root, "skipped_self": skipped_self}


def add_alias(conn: sqlite3.Connection, old_name: str, new_name: str,
              renamed_at: str, note: str = "") -> bool:
    """Record a rename. Returns False if the pair is already declared."""
    try:
        conn.execute(
            "INSERT INTO entity_aliases (old_name, new_name, renamed_at, note, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (old_name.strip(), new_name.strip(), renamed_at, note,
             datetime.now(timezone.utc).replace(tzinfo=None).isoformat()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def list_aliases(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM entity_aliases ORDER BY renamed_at")]


def _word(name: str) -> re.Pattern:
    """Whole-word match that survives names with non-word edges ('C++',
    'x-'): \\b between '+' and space never matches, so fall back to
    whitespace lookarounds on non-word boundaries."""
    name = name.strip()
    pre = r"\b" if re.match(r"\w", name[:1] or "") else r"(?<!\S)"
    suf = r"\b" if re.match(r"\w", name[-1:] or "") else r"(?!\S)"
    return re.compile(pre + re.escape(name) + suf, re.IGNORECASE)


def triage_alias(conn: sqlite3.Connection, alias: dict, k: int = 5,
                 config: dict | None = None) -> dict:
    """Classify every live dead-name reference for one alias, and measure
    serving-side leakage. Read-only on cubes; deterministic."""
    old_rx, new_rx = _word(alias["old_name"]), _word(alias["new_name"])
    rows = conn.execute(
        "SELECT id, title, content, created_at FROM helicon_cubes "
        "WHERE review_status IN ('pending', 'revised', 'approved') "
        "AND merged_into IS NULL AND (content LIKE ? OR title LIKE ?)",
        (f"%{alias['old_name']}%", f"%{alias['old_name']}%"),
    ).fetchall()

    # All comparisons in UTC-naive space: the store mixes naive, 'Z' and
    # '+HH:MM' stamps (raw string compare misfiled the ±2h band around the
    # rename). Unparseable stamps ('{{date}}' template garbage) normalize to
    # "" = oldest = history — the safe side.
    from helicon.timeutil import ts_norm
    renamed_norm = ts_norm(alias["renamed_at"]) or alias["renamed_at"]

    history, rename_aware, current_claims = [], [], []
    for r in rows:
        text = f"{r['title'] or ''}\n{r['content'] or ''}"
        if not old_rx.search(text):
            continue  # LIKE prefilter caught a substring ('glazed'), not the name
        if ts_norm(r["created_at"]) < renamed_norm:
            history.append(r)
        elif new_rx.search(text):
            rename_aware.append(r)
        else:
            current_claims.append(r)

    # Serving side: what an agent retrieving for the CURRENT name gets.
    leaked = []
    try:
        from helicon.snapshots import _retrieve
        hits = _retrieve(conn, alias["new_name"], k)
        for h in hits:
            row = conn.execute(
                "SELECT title, content FROM helicon_cubes WHERE id = ?",
                (h["id"],)).fetchone()
            text = f"{row['title'] or ''}\n{row['content'] or ''}" if row else ""
            if old_rx.search(text) and not new_rx.search(text):
                leaked.append(h)
    except Exception:
        hits = []

    code = code_refs(alias["old_name"], alias["new_name"],
                     repos_dir=repos_dir_from_config(config))

    return {
        "old_name": alias["old_name"], "new_name": alias["new_name"],
        "renamed_at": alias["renamed_at"],
        "code_leads": code["leads"], "code_legacy_tests": code["legacy_tests"],
        "code_repos": code["repos"], "code_scanned": code["scanned"],
        "live_refs": len(history) + len(rename_aware) + len(current_claims),
        "history": len(history),
        "rename_aware": len(rename_aware),
        "current_claims": len(current_claims),
        "current_claim_samples": [
            {"id": r["id"], "title": (r["title"] or "")[:70],
             "created_at": r["created_at"]}
            for r in sorted(current_claims,
                            key=lambda r: r["created_at"] or "", reverse=True)[:5]],
        "retrieved_for_new_name": len(hits),
        "leaked": [{"id": h["id"], "title": h.get("title", "")[:70]} for h in leaked],
    }


def alias_rot(conn: sqlite3.Connection, k: int = 5,
              config: dict | None = None) -> list[dict]:
    """Triage every declared alias. The rot exam's R4 raw material."""
    return [triage_alias(conn, a, k=k, config=config) for a in list_aliases(conn)]


def _existing_alias_keys(conn: sqlite3.Connection) -> set[str]:
    keys = set()
    for row in conn.execute(
        "SELECT details FROM audit_log WHERE audit_type = 'supersession'"
    ):
        try:
            key = json.loads(row["details"]).get("alias_key")
            if key:
                keys.add(key)
        except (json.JSONDecodeError, TypeError):
            pass
    return keys


def alias_scan(conn: sqlite3.Connection, k: int = 5,
               config: dict | None = None) -> dict:
    """File one audit finding per alias that shows rot (current-claims or
    serving leakage). Idempotent by alias_key."""
    existing = _existing_alias_keys(conn)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    filed, clean, skipped = [], [], []

    for t in alias_rot(conn, k=k, config=config):
        key = f"{t['old_name'].lower()}->{t['new_name'].lower()}"
        if t["current_claims"] == 0 and not t["leaked"]:
            clean.append(key)
            continue
        if key in existing:
            skipped.append(key)
            continue
        finding = AuditResult(
            audit_type="supersession",
            target_type="entity",
            target_id=key,
            finding=(f"Dead name '{t['old_name']}' still asserted as current: "
                     f"{t['current_claims']} live memor{'y' if t['current_claims'] == 1 else 'ies'} written AFTER the rename "
                     f"to '{t['new_name']}' use only the old name"
                     + (f"; {len(t['leaked'])}/{t['retrieved_for_new_name']} top-{k} "
                        f"hits for '{t['new_name']}' serve the dead name"
                        if t["leaked"] else "")
                     + f" ({t['history']} pre-rename ref(s) kept as history)"),
            severity="warning" if not t["leaked"] else "critical",
            proposed_action="flag",
            details={"alias_key": key, **{k2: v for k2, v in t.items()
                                          if k2 != "current_claim_samples"},
                     "samples": t["current_claim_samples"]},
            audited_at=now,
        )
        insert_audit(conn, finding)
        filed.append({"alias_key": key, "finding": finding.finding})
    conn.commit()
    return {"filed": filed, "already_filed": skipped, "clean": clean}
