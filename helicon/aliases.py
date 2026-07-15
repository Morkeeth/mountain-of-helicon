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
# R4 reported 341 RELAY current-claims as a COUNT. At least one was load-bearing
# in running code: tasks post as poster:"agent:relay", which strips to
# agentId="relay", which hits getAgent("relay"), which finds no such key in
# AGENT_REGISTRY and returns null — silently, no error, no log. 107 production
# tasks carried agent:null for 13 days and eight named agents never fired once.
# A dead name you can read past is prose. A dead name a lookup executes is an
# outage. That distinction did not exist here.
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


def code_refs(old_name: str, new_name: str = "", repos_dir: str = "~/CODE",
              cap: int = 60) -> dict:
    """Where the dead name is EXECUTABLE, not merely written."""
    root = os.path.expanduser(repos_dir)
    rx = _code_rx(old_name)
    # Same rule the prose triage already uses: a line naming BOTH the old and
    # the new name is rename-AWARE (a migration, an alias declaration, a compat
    # shim). It is about the rename, so it is not a dead reference.
    new_rx = re.compile(r"\b" + re.escape(new_name) + r"\b", re.I) if new_name else None
    leads, legacy, repos = [], 0, 0
    if not os.path.isdir(root):
        return {"leads": [], "legacy_tests": 0, "repos": 0}
    for entry in sorted(os.listdir(root)):
        repo = os.path.join(root, entry)
        if not os.path.isdir(os.path.join(repo, ".git")):
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
    return {"leads": leads, "legacy_tests": legacy, "repos": repos}


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


def triage_alias(conn: sqlite3.Connection, alias: dict, k: int = 5) -> dict:
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

    code = code_refs(alias["old_name"], alias["new_name"])

    return {
        "old_name": alias["old_name"], "new_name": alias["new_name"],
        "renamed_at": alias["renamed_at"],
        "code_leads": code["leads"], "code_legacy_tests": code["legacy_tests"],
        "code_repos": code["repos"],
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


def alias_rot(conn: sqlite3.Connection, k: int = 5) -> list[dict]:
    """Triage every declared alias. The rot exam's R4 raw material."""
    return [triage_alias(conn, a, k=k) for a in list_aliases(conn)]


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


def alias_scan(conn: sqlite3.Connection, k: int = 5) -> dict:
    """File one audit finding per alias that shows rot (current-claims or
    serving leakage). Idempotent by alias_key."""
    existing = _existing_alias_keys(conn)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    filed, clean, skipped = [], [], []

    for t in alias_rot(conn, k=k):
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
