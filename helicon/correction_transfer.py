"""Human-reviewed correction transfer with exact, inspectable scope.

This is deliberately deterministic.  It does not infer a rule with a model:
the edited words, proposed rule, declared scope, and mechanical replacement
are all visible before acceptance.  Attempts only receive currently accepted
rules whose complete scope matches their declared context.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid


class TransferError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _actor(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TransferError("An explicit actor is required.")
    return value.strip()


def _text(value: str, label: str, *, required: bool = True) -> str:
    if not isinstance(value, str) or (required and not value.strip()):
        raise TransferError(f"{label} is required.")
    if "\x00" in value:
        raise TransferError(f"{label} cannot contain NUL.")
    return value.strip()


def normalize_scope(scope: dict[str, str]) -> dict[str, str]:
    if not isinstance(scope, dict) or not scope:
        raise TransferError("At least one explicit scope label is required.")
    result: dict[str, str] = {}
    for key, value in scope.items():
        if not isinstance(key, str) or not isinstance(value, str) or not key.strip() or not value.strip():
            raise TransferError("Scope labels and values must be non-empty text.")
        result[key.strip()] = value.strip()
    return dict(sorted(result.items()))


_TOKENS = re.compile(r"\w+(?:[-'’]\w+)*|[^\w\s]", re.UNICODE)


def word_delta(before: str, after: str) -> list[dict[str, str]]:
    """Return only changed lexical runs; unchanged prose is not disguised as a delta."""
    left, right = _TOKENS.findall(before), _TOKENS.findall(after)
    changes: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=left, b=right).get_opcodes():
        if tag in ("replace", "delete"):
            changes.append({"kind": "removed", "text": " ".join(left[i1:i2])})
        if tag in ("replace", "insert"):
            changes.append({"kind": "added", "text": " ".join(right[j1:j2])})
    return changes


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class CorrectionTransferStore:
    """Append-audited local rule store. Source drafts are never stored implicitly."""

    def __init__(self, state_dir):
        self.state_dir = Path(state_dir).expanduser().resolve()
        self.db_path = self.state_dir / "correction-transfer.sqlite3"

    def _initialize(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS correction_rules "
                "(id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL, "
                "events TEXT NOT NULL, created_at TEXT NOT NULL)"
            )

    @contextmanager
    def _db(self, readonly: bool = False):
        db = (
            sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True, timeout=30)
            if readonly
            else sqlite3.connect(self.db_path, timeout=30)
        )
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def _row(self, ident: str):
        if not self.db_path.exists():
            raise TransferError("Unknown correction rule.")
        with self._db(readonly=True) as db:
            row = db.execute("SELECT * FROM correction_rules WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise TransferError("Unknown correction rule.")
        return row

    @staticmethod
    def _public(row) -> dict:
        return {
            **json.loads(row["payload"]),
            "status": row["status"],
            "events": json.loads(row["events"]),
        }

    def _event(self, ident: str, status: str, actor: str, detail: str = "") -> dict:
        row = self._row(ident)
        events = json.loads(row["events"])
        events.append({"status": status, "actor": actor, "at": _now(), "detail": detail})
        with self._db() as db:
            db.execute(
                "UPDATE correction_rules SET status=?, events=? WHERE id=?",
                (status, json.dumps(events), ident),
            )
        return self._public(self._row(ident))

    def propose(
        self,
        *,
        original_draft: str,
        edited_draft: str,
        proposed_rule: str,
        scope: dict[str, str],
        operation: dict[str, str],
        actor: str,
        explicit_instruction: str = "",
        inferred_reason: str = "",
        supersedes: str | None = None,
        example_label: str = "",
    ) -> dict:
        actor = _actor(actor)
        original = _text(original_draft, "Original draft")
        edited = _text(edited_draft, "Edited draft")
        if original == edited:
            raise TransferError("The edited draft must differ from the original.")
        rule = _text(proposed_rule, "Proposed rule")
        explicit = _text(explicit_instruction, "Explicit instruction", required=False)
        inferred = _text(inferred_reason, "Inferred reason", required=False)
        scoped = normalize_scope(scope)
        if not isinstance(operation, dict):
            raise TransferError("A visible replacement operation is required.")
        find = _text(operation.get("find", ""), "Replacement source")
        replace = _text(operation.get("replace", ""), "Replacement target", required=False)
        if find == replace or find not in original or original.replace(find, replace) != edited:
            raise TransferError("The visible replacement must exactly reproduce the edited draft.")
        if supersedes:
            previous = self._public(self._row(supersedes))
            if previous["status"] != "accepted":
                raise TransferError("Only an accepted rule can be superseded.")

        self._initialize()
        ident = "ctr_" + uuid.uuid4().hex
        created = _now()
        payload = {
            "id": ident,
            "original_draft": original,
            "edited_draft": edited,
            "word_delta": word_delta(original, edited),
            "proposed_rule": rule,
            "scope": scoped,
            "operation": {"find": find, "replace": replace},
            "explicit_instruction": explicit or None,
            "inferred_reason": inferred or None,
            "reason_authority": {
                "explicit_instruction": "human-authored" if explicit else "absent",
                "inferred_reason": "agent-inferred; not an instruction" if inferred else "absent",
            },
            "supersedes": supersedes,
            "example_label": _text(example_label, "Example label", required=False) or None,
            "created_at": created,
            "draft_hashes": {"original": _digest(original), "edited": _digest(edited)},
        }
        events = [{"status": "proposed", "actor": actor, "at": created, "detail": "No later attempt changed."}]
        with self._db() as db:
            db.execute(
                "INSERT INTO correction_rules VALUES (?,?,?,?,?)",
                (ident, json.dumps(payload), "proposed", json.dumps(events), created),
            )
        return self._public(self._row(ident))

    def decide(self, ident: str, decision: str, actor: str) -> dict:
        actor = _actor(actor)
        if decision not in ("accept", "reject"):
            raise TransferError("Decision must be accept or reject.")
        row = self._row(ident)
        if row["status"] != "proposed":
            raise TransferError("Only a proposed rule can be accepted or rejected.")
        status = "accepted" if decision == "accept" else "rejected"
        result = self._event(ident, status, actor, "Human decision.")
        if status == "accepted" and result.get("supersedes"):
            self._event(result["supersedes"], "superseded", actor, f"Superseded by {ident}.")
        return self._public(self._row(ident))

    def change_scope(self, ident: str, scope: dict[str, str], actor: str) -> dict:
        """Change a pending proposal. Accepted scope changes require supersession."""
        actor = _actor(actor)
        row = self._row(ident)
        if row["status"] != "proposed":
            raise TransferError("Accepted scope is immutable; supersede the rule instead.")
        payload = json.loads(row["payload"])
        payload["scope"] = normalize_scope(scope)
        with self._db() as db:
            db.execute("UPDATE correction_rules SET payload=? WHERE id=?", (json.dumps(payload), ident))
        return self._event(ident, "proposed", actor, "Scope changed before decision.")

    def undo(self, ident: str, actor: str) -> dict:
        actor = _actor(actor)
        row = self._row(ident)
        if row["status"] not in ("accepted", "rejected"):
            raise TransferError("Only an accepted or rejected decision can be undone.")
        payload = json.loads(row["payload"])
        result = self._event(ident, "undone", actor, f"Undid {row['status']} decision.")
        prior_id = payload.get("supersedes")
        if row["status"] == "accepted" and prior_id:
            prior = self._row(prior_id)
            if prior["status"] == "superseded":
                self._event(prior_id, "accepted", actor, f"Restored after undoing {ident}.")
        return result

    def get(self, ident: str) -> dict:
        return self._public(self._row(ident))

    def list(self) -> list[dict]:
        if not self.db_path.exists():
            return []
        with self._db(readonly=True) as db:
            return [self._public(row) for row in db.execute(
                "SELECT * FROM correction_rules ORDER BY created_at DESC"
            ).fetchall()]

    def attempt(self, *, draft: str, context: dict[str, str]) -> dict:
        baseline = _text(draft, "Draft")
        supplied = normalize_scope(context)
        result = baseline
        applied: list[dict] = []
        # Oldest first makes multiple accepted lessons deterministic.
        for rule in reversed(self.list()):
            if rule["status"] != "accepted":
                continue
            if not all(supplied.get(key) == value for key, value in rule["scope"].items()):
                continue
            operation = rule["operation"]
            if operation["find"] not in result:
                continue
            result = result.replace(operation["find"], operation["replace"])
            applied.append({"rule_id": rule["id"], "rule": rule["proposed_rule"], "scope": rule["scope"]})
        return {
            "frozen_baseline": baseline,
            "baseline_sha256": _digest(baseline),
            "result": result,
            "result_sha256": _digest(result),
            "changed": result != baseline,
            "context": supplied,
            "applied_rules": applied,
            "evidence": "matched accepted rule" if applied else "no accepted rule matched the complete scope",
        }

    def compare(self, cases: list[dict]) -> dict:
        if not isinstance(cases, list) or not cases:
            raise TransferError("At least one comparison case is required.")
        results = []
        for case in cases:
            if not isinstance(case, dict):
                raise TransferError("Each case must be an object.")
            attempt = self.attempt(draft=case.get("draft", ""), context=case.get("context", {}))
            results.append({"label": _text(case.get("label", ""), "Case label"), **attempt})
        return {
            "cases": results,
            "claim_limit": (
                "These authored cases show deterministic scope behavior only. "
                "Personal benefit and reduced editing are untested."
            ),
        }


AUTHORED_EXAMPLE = {
    "example_label": "Authored example — synthetic, not Oscar's corpus",
    "original_draft": "We shipped scoped correction transfer.",
    "edited_draft": "We built scoped correction transfer.",
    "explicit_instruction": "In Helicon progress updates, use “built”, not “shipped”, until it is hosted.",
    "inferred_reason": "The wording may distinguish completed implementation from hosted availability.",
    "proposed_rule": "For Helicon progress updates, replace “shipped” with “built”.",
    "scope": {"project": "mountain-of-helicon", "task": "progress-update"},
    "operation": {"find": "shipped", "replace": "built"},
    "cases": [
        {
            "label": "Later relevant progress update",
            "draft": "We shipped the correction history.",
            "context": {"project": "mountain-of-helicon", "task": "progress-update"},
        },
        {
            "label": "Different release context — explicit non-transfer",
            "draft": "We shipped version 0.2 to package users.",
            "context": {"project": "mountain-of-helicon", "task": "release-note"},
        },
    ],
}
