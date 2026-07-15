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
import re
import sqlite3
from datetime import datetime, timezone

from helicon.models import AuditResult
from helicon.db import insert_audit


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

    return {
        "old_name": alias["old_name"], "new_name": alias["new_name"],
        "renamed_at": alias["renamed_at"],
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
