"""The valuation gate — govern-by-exception, made real (V2.3).

The product vision's tier 1: the engine auto-handles the bulk and the human sees
only genuine exceptions. Today the engine escalates by PATTERN ("looks like
rot") regardless of whether it matters, which is why the queue is hundreds deep
instead of "a handful per day".

A finding earns a human ONLY if all three gates hold:

  CONSEQUENCE   the memory it is about is still live and reachable
  NEEDS_HUMAN   it cannot be resolved mechanically from what Helicon already knows
  STILL_TRUE    the asserted condition re-verifies right now

Measured against the real store on 2026-07-22 — 335 open findings:
  · 227 (68%) were about memories ALREADY KILLED. A ruling on a dead memory
    changes nothing, so it was never a question for a human.
  · 88 "decay/critical" findings, every one on a killed memory, sat unread for
    a month while being labelled critical.
The queue was not a queue. It was a pattern log wearing a queue's clothes.

Two deliberate design choices, both load-bearing:

1. A machine decision NEVER writes `audit_log.human_decision`. `gold.py`
   compiles the Golden Rules from `WHERE human_decision IS NOT NULL` — writing
   there would forge operator rulings into the stack's law. Machine outcomes get
   their own columns, so the law stays human and the retirement stays auditable.

2. Gate 3 re-verifies the claim instead of learning from the operator's silence.
   Silence is not preference here: with 227 noise items on top, "he never ruled
   on temporal findings" is evidence the queue was unusable, not evidence that
   temporal findings are worthless. Confidence has to come from re-checking the
   world, not from a resolution rate the noise itself suppressed.
"""
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone

# Retired memory. A finding about one of these has no consequence: whatever the
# human decided, the memory is already out of every retrieval path.
DEAD_STATUSES = ("killed", "superseded")


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Add the machine-decision columns if absent. Idempotent, additive, and
    deliberately separate from human_decision (see the module docstring)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(audit_log)")}
    for col in ("machine_decision", "machine_reason", "machine_decided_at",
                "machine_batch_id"):
        if col not in cols:
            conn.execute(f"ALTER TABLE audit_log ADD COLUMN {col} TEXT")
    conn.commit()


# ---------------------------------------------------------------- the gates

def _consequence(conn, row) -> tuple[bool, str]:
    """Is the memory this finding is about still live and reachable?"""
    if row["target_type"] != "cube":
        # Not a memory at all (a routine, a path, a session). Nothing to check
        # here — consequence is decided by the later gates.
        return True, ""
    cube = conn.execute(
        "SELECT review_status FROM helicon_cubes WHERE id = ?", (row["target_id"],)
    ).fetchone()
    if cube is None:
        return False, "the memory it points at no longer exists"
    if cube["review_status"] in DEAD_STATUSES:
        return False, f"the memory is already {cube['review_status']}"
    return True, ""


_QUOTED = re.compile(r"'([^']*)'")


def _subject(row) -> str:
    """WHO the finding is about. The quoted name if there is one, else the target
    id. Never normalised away — the subject is the identity of the fact."""
    m = _QUOTED.search(row["finding"] or "")
    if m:
        return m.group(1).strip().lower()
    return (row["target_id"] or "").strip().lower()


def _shape(text: str) -> str:
    """What the finding says, retaining measurements as part of the claim.

    A later measurement can cross a consequential threshold: dismissing 61h of
    silence must not automatically dismiss 200h. Precedent therefore suppresses
    only an exact repeated claim, after whitespace/case normalization.
    """
    return " ".join((text or "").lower().split())


_RENAME_FINDING = re.compile(
    r"\b(?:dead path|missing path|no longer exists|renamed|old name|stale path)\b",
    re.I,
)


def _mentions_alias(text: str, alias: str) -> bool:
    """Match an alias as a token/path component, never as a substring."""
    return bool(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text, re.I))


def _needs_human(conn, row) -> tuple[bool, str]:
    """Can Helicon resolve this from what it already knows?

    Two things it already knows, both from the operator's own past rulings:

    1. A RENAME. `~/CODE/glaze/...` is missing because he renamed glaze to
       helicon on Jul 4 and ruled on it. Asking again is asking him to re-decide
       a decision the store is already holding.

    2. A DISMISSED PRECEDENT. `gold.py` compiles dismissals into the Golden
       Rules' "what is NOT rot here" section. A finding that re-raises one is
       the engine ignoring the law it publishes — the single most corrosive
       thing a governance tool can do to its own credibility.
    """
    finding = (row["finding"] or "").lower()
    if _RENAME_FINDING.search(finding):
        for alias in conn.execute("SELECT old_name, new_name FROM entity_aliases"):
            old = (alias["old_name"] or "").strip().lower()
            if old and _mentions_alias(finding, old):
                return False, (f"explained by the {alias['old_name']} -> "
                               f"{alias['new_name']} rename you already ruled")

    shape, subject = _shape(row["finding"]), _subject(row)
    for prior in conn.execute(
            "SELECT audit_type, target_id, finding FROM audit_log "
            "WHERE human_decision LIKE 'dismissed%'"):
        # Same subject AND same claim. Either alone is not enough: same subject
        # with a different claim is a new question about a known thing, and the
        # same claim about a different subject is a different fact entirely.
        if (prior["audit_type"] == row["audit_type"]
                and _subject(prior) == subject
                and _shape(prior["finding"]) == shape):
            return False, f"you already dismissed this exact finding about {subject!r}"
    return True, ""


def _still_true(conn, row) -> tuple[bool, str]:
    """Does the asserted condition re-verify right now?

    Only claims that are cheap and safe to re-check are re-checked; anything
    else passes rather than being silently dropped on a guess. A gate that
    guesses would retire real findings, which is worse than a queue that is
    too long.
    """
    finding = row["finding"] or ""
    if "dead path" in finding.lower():
        # The claim is "this path does not exist". Verify it literally.
        for token in finding.replace("(", " ").replace(")", " ").replace(",", " ").split():
            if token.startswith("/") and len(token) > 8:
                if os.path.exists(os.path.expanduser(token)):
                    return False, "the path exists again"
                return True, ""
    return True, ""


GATES = (
    ("consequence", _consequence),
    ("needs_human", _needs_human),
    ("still_true", _still_true),
)


def evaluate(conn, row) -> dict:
    """Run one finding through the three gates. First failure wins, so the
    reason a human never sees it is always a single, statable sentence."""
    for name, gate in GATES:
        ok, why = gate(conn, row)
        if not ok:
            return {"escalate": False, "gate": name, "reason": why}
    return {"escalate": True, "gate": "", "reason": ""}


# ------------------------------------------------------------------ the pass

def triage_open(conn, apply: bool = False) -> dict:
    """Evaluate every open finding. Dry by default — `apply=True` records the
    machine decision so the queue stops showing it. Nothing is deleted, and
    `helicon queue --undo` puts every one of them back."""
    ensure_schema(conn)
    batch_id = uuid.uuid4().hex if apply else None
    if apply:
        conn.execute("BEGIN IMMEDIATE")
    try:
        rows = conn.execute(
            """SELECT id, audit_type, target_type, target_id, finding, severity
               FROM audit_log
               WHERE human_decision IS NULL AND machine_decision IS NULL"""
        ).fetchall()

        escalate, retire = [], []
        for r in rows:
            verdict = evaluate(conn, r)
            (escalate if verdict["escalate"] else retire).append((r, verdict))

        if apply:
            now = _now()
            conn.executemany(
                "UPDATE audit_log SET machine_decision='auto-retired', "
                "machine_reason=?, machine_decided_at=?, machine_batch_id=? "
                "WHERE id=? AND human_decision IS NULL AND machine_decision IS NULL",
                [(v["reason"], now, batch_id, r["id"]) for r, v in retire])
            conn.commit()
    except Exception:
        if apply:
            conn.rollback()
        raise

    by_gate: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for r, v in retire:
        by_gate[v["gate"]] = by_gate.get(v["gate"], 0) + 1
    for r, _ in escalate:
        by_type[r["audit_type"]] = by_type.get(r["audit_type"], 0) + 1

    return {
        "considered": len(rows),
        "escalated": len(escalate),
        "auto_retired": len(retire),
        "applied": apply,
        "batch_id": batch_id,
        "retired_by_gate": by_gate,
        "escalated_by_type": by_type,
        "samples": [{"id": r["id"], "type": r["audit_type"],
                     "finding": (r["finding"] or "")[:88], "reason": v["reason"]}
                    for r, v in retire[:5]],
    }


def undo(conn, batch_id: str | None = None) -> int:
    """Restore one valuation batch (the latest by default), never other machine
    decisions. A reversible gate must not become a global machine-state reset."""
    ensure_schema(conn)
    if batch_id is None:
        row = conn.execute(
            "SELECT machine_batch_id FROM audit_log "
            "WHERE machine_decision='auto-retired' "
            "ORDER BY machine_decided_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return 0
        batch_id = row["machine_batch_id"]
    if batch_id is None:
        where, params = (
            "machine_decision='auto-retired' AND machine_batch_id IS NULL", ()
        )
    else:
        where, params = (
            "machine_decision='auto-retired' AND machine_batch_id=?", (batch_id,)
        )
    n = conn.execute(f"SELECT COUNT(*) FROM audit_log WHERE {where}", params).fetchone()[0]
    conn.execute(
        f"UPDATE audit_log SET machine_decision=NULL, machine_reason=NULL, "
        f"machine_decided_at=NULL, machine_batch_id=NULL WHERE {where}", params
    )
    conn.commit()
    return n


def format_result(res: dict) -> str:
    """Zen output: the number, the consequence, the action. No table dump."""
    lines = []
    kept, cut = res["escalated"], res["auto_retired"]
    lines.append(f"  {res['considered']} open findings considered")
    lines.append(f"  {kept} need you · {cut} auto-handled"
                 + ("" if res["applied"] else "   (dry run — nothing written)"))
    if res["retired_by_gate"]:
        lines.append("")
        lines.append("  auto-handled because:")
        label = {"consequence": "no consequence (memory already retired/gone)",
                 "needs_human": "already settled by a rename or a dismissal of yours",
                 "still_true": "no longer true when re-checked"}
        for gate, n in sorted(res["retired_by_gate"].items(), key=lambda x: -x[1]):
            lines.append(f"    {n:>4}  {label.get(gate, gate)}")
    if res["escalated_by_type"]:
        lines.append("")
        lines.append("  what still needs your judgment:")
        for t, n in sorted(res["escalated_by_type"].items(), key=lambda x: -x[1]):
            lines.append(f"    {n:>4}  {t}")
    if not res["applied"] and cut:
        lines.append("")
        lines.append("  apply with: helicon queue --apply   (reversible: helicon queue --undo)")
    return "\n".join(lines)
