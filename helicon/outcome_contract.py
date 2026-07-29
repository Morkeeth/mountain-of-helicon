"""Outcome Contract — what a run must promise BEFORE it earns the right to start.

Helicon's line (VISION.md): it measures whether activity earns the right to
*continue*, not activity itself. A governed run already freezes an acceptance
test — "what does 'accepted' mean". The Outcome Contract widens that from "did
the work pass" to "was the work worth doing, and can we SEE whether it changed
anything in the real world":

  beneficiary        — who is this run FOR? a person or system that ends up better off
  observable_change  — what real-world change should it cause?
  evidence_source    — where will we look to confirm it? (the OUTCOME, not the artifact)
  decision_owner     — who rules on the result?
  time_horizon       — by when do we expect to observe the change?

Honesty rules, same as everywhere in this repo:
- No field is invented or defaulted to a plausible-looking value. A blank field
  is reported blank, so the pre-run gate can refuse a run that cannot be judged.
- This is metadata about INTENT and OBSERVATION. It is deliberately NOT part of
  a run's `task_spec_hash`: a run's A/B identity is its objective / model /
  harness / skills, not who it was for. Two runs for different beneficiaries are
  still the same task for comparison purposes.

Pure module: no DB, no network. `taskrun` stores the JSON on the run;
`intervention` reads a validated contract to decide if a run may start.
"""
import json

# Every field the contract can carry, in display order.
FIELDS = (
    "beneficiary",
    "observable_change",
    "evidence_source",
    "decision_owner",
    "time_horizon",
)

# The core that makes an outcome JUDGEABLE. Without a beneficiary the run is for
# no one; without an observable change + an evidence source there is no way to
# tell whether it changed reality (the two failure modes the gate must block).
REQUIRED = ("beneficiary", "observable_change", "evidence_source")

# Strongly advised, but a run can proceed with a warning rather than a block:
# who rules on it, and by when we expect to see the change.
RECOMMENDED = ("decision_owner", "time_horizon")

_LABELS = {
    "beneficiary": "who it's for",
    "observable_change": "the real-world change",
    "evidence_source": "where we'll confirm it",
    "decision_owner": "who rules on it",
    "time_horizon": "by when",
}


def label(field: str) -> str:
    return _LABELS.get(field, field)


def normalize(contract) -> dict:
    """Coerce input into a clean {field: non-empty str} dict. Unknown keys are
    dropped; blank/whitespace values are treated as absent (never stored as a
    fake-present empty string)."""
    if not isinstance(contract, dict):
        return {}
    out = {}
    for f in FIELDS:
        v = contract.get(f)
        if isinstance(v, str) and v.strip():
            out[f] = v.strip()
    return out


def validate(contract) -> dict:
    """Report exactly which fields are present and which are missing. No guessing,
    no defaults — a missing field is missing so the gate can act on the truth."""
    c = normalize(contract)
    present = [f for f in FIELDS if f in c]
    missing = [f for f in FIELDS if f not in c]
    missing_required = [f for f in REQUIRED if f not in c]
    missing_recommended = [f for f in RECOMMENDED if f not in c]
    return {
        "contract": c,
        "present": present,
        "missing": missing,
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "complete": not missing,
        "has_beneficiary": "beneficiary" in c,
        # "can we observe an outcome" = a stated change AND a place to confirm it
        "observable": "observable_change" in c and "evidence_source" in c,
    }


def dumps(contract) -> str | None:
    """Serialize a normalized contract for storage, or None when empty (so an
    absent contract is NULL in the DB, not an empty-object lie)."""
    c = normalize(contract)
    return json.dumps(c, sort_keys=True) if c else None


def loads(blob) -> dict:
    """Parse a stored contract blob back to a dict; tolerant of NULL/garbage."""
    if not blob:
        return {}
    try:
        return normalize(json.loads(blob))
    except (json.JSONDecodeError, TypeError):
        return {}


def from_kwargs(**kwargs) -> dict:
    """Build a contract dict from named args (the CLI/API shape), keeping only
    known, non-empty fields."""
    return normalize({f: kwargs.get(f) for f in FIELDS})
