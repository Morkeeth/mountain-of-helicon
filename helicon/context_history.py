"""Explicit, local snapshots of source reviews and conservative change comparison.

This is separate from retrieval snapshots in ``snapshots.py``: it pins the
review envelope, source revisions, check coverage and references to rulings.
Reading history never runs a scan, updates a source clock or creates storage.
Only ``save`` writes. The caller owns the local storage directory and must not
publish it: review evidence can contain private context.

Coverage contract: ``checks=[{id, version, status, source_ids}]``. Absence is
evidence only when the same successful check/version covered the same source
identities in both reviews. Findings name ``check_id`` or ``check_ids``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from datetime import datetime


SCHEMA = "helicon.context-history/1"
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class HistoryError(ValueError):
    """An invalid, changed or corrupt review cannot supply comparison evidence."""


def _bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _time(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("missing timezone")
        return result
    except (ValueError, AttributeError) as exc:
        raise HistoryError("Review observed_at must include a timezone") from exc


def _indexed(rows: list, label: str) -> dict:
    if not isinstance(rows, list) or any(not isinstance(r, dict) or not r.get("id") for r in rows):
        raise HistoryError(f"{label} need nonempty IDs")
    result = {r["id"]: r for r in rows}
    if len(result) != len(rows):
        raise HistoryError(f"Duplicate {label} ID")
    return result


def _validate(review: dict) -> None:
    if not isinstance(review, dict) or not review.get("schema") or not review.get("project"):
        raise HistoryError("Review requires schema and project")
    _time(review.get("observed_at"))
    sources = _indexed(review.get("sources"), "sources")
    findings = _indexed(review.get("findings"), "findings")
    for source in sources.values():
        if not isinstance(source.get("path"), str) or not Path(source["path"]).is_absolute():
            raise HistoryError("Source paths must be absolute")
        sha = source.get("sha256")
        if sha is not None and (not isinstance(sha, str) or not _HASH.fullmatch(sha)):
            raise HistoryError("Invalid source SHA256")
    for finding in findings.values():
        for evidence in finding.get("evidence", []):
            source = sources.get(evidence.get("source_id"))
            if source is None or evidence.get("path") != source["path"] or evidence.get("sha256") != source.get("sha256"):
                raise HistoryError("Finding evidence must match its exact source revision")
    coverage = review.get("coverage")
    if not isinstance(coverage, dict):
        raise HistoryError("Review requires coverage")
    checks = _indexed(coverage.get("checks", []), "checks")
    for check in checks.values():
        ids = check.get("source_ids", [])
        if not isinstance(ids, list) or any(s not in sources for s in ids):
            raise HistoryError("Check coverage names unknown sources")


def _revalidate_sources(review: dict) -> list[dict]:
    validations = []
    for source in review["sources"]:
        path = Path(source["path"])
        expected = source.get("sha256")
        if expected:
            try:
                actual = _digest(path.read_bytes())
            except OSError as exc:
                raise HistoryError(f"Reviewed source is unavailable: {source['id']}") from exc
            if actual != expected:
                raise HistoryError(f"Reviewed source changed: {source['id']}")
            state = "matched"
        elif source.get("status") == "missing":
            if path.exists() or path.is_symlink():
                raise HistoryError(f"Previously missing source now exists: {source['id']}")
            state = "still_missing"
        else:
            state = "unverified"
        validations.append({"source_id": source["id"], "status": state})
    return validations


def _checks(finding: dict) -> list[str]:
    return finding.get("check_ids") or ([finding["check_id"]] if finding.get("check_id") else [])


def _absence_checked(finding: dict, previous: dict, current: dict) -> bool:
    """Do not infer a clean scan from a missing finding or aggregate count."""
    wanted = _checks(finding)
    if not wanted:
        return False
    before = {c["id"]: c for c in previous["coverage"].get("checks", [])}
    after = {c["id"]: c for c in current["coverage"].get("checks", [])}
    source_before = {s["id"]: s for s in previous["sources"]}
    source_after = {s["id"]: s for s in current["sources"]}
    evidence_ids = {e["source_id"] for e in finding.get("evidence", [])}
    if not evidence_ids:
        return False
    covered = set()
    for check_id in wanted:
        old, new = before.get(check_id, {}), after.get(check_id, {})
        population = set(old.get("source_ids", []))
        if (old.get("status") != "success" or new.get("status") != "success"
                or not old.get("version") or old.get("version") != new.get("version")
                or not population or population != set(new.get("source_ids", []))):
            return False
        for source_id in population:
            a, b = source_before.get(source_id, {}), source_after.get(source_id, {})
            if not a.get("sha256") or not b.get("sha256") or a.get("path") != b.get("path"):
                return False
        covered.update(population)
    return evidence_ids <= covered


class ContextHistory:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().absolute()

    def save(self, review: dict, ruling_refs: list[dict] | None = None) -> dict:
        """Explicit save; reject source drift, then publish one immutable file.

        Ruling references are existing records, never a new decision database.
        Each reference supplies ``finding_id`` and ``ref``; optional verdict,
        note and original revision remain attributed caller-supplied evidence.
        """
        review = json.loads(_bytes(review))  # detach caller-owned mutable data
        _validate(review)
        refs = json.loads(_bytes(ruling_refs or []))
        if not isinstance(refs, list) or any(not isinstance(r, dict) or not r.get("finding_id") or not r.get("ref") for r in refs):
            raise HistoryError("Ruling references require finding_id and ref")
        payload = {"schema": SCHEMA, "review": review, "ruling_refs": refs,
                   "source_validation": _revalidate_sources(review)}
        sha = _digest(_bytes(payload))
        snapshot = {"id": sha, "sha256": sha, **payload}
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = self.root / f"{sha}.json"
        fd, temporary = tempfile.mkstemp(prefix=".snapshot-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(_bytes(snapshot))
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, destination)  # exclusive publication, no overwrite
            except FileExistsError:
                self.load(sha)  # refuse a corrupt object at the existing ID
        finally:
            os.unlink(temporary)
        return self.load(sha)

    def load(self, snapshot_id: str) -> dict:
        if not isinstance(snapshot_id, str) or not _HASH.fullmatch(snapshot_id):
            raise HistoryError("Invalid snapshot ID")
        path = self.root / f"{snapshot_id}.json"
        if path.is_symlink():
            raise HistoryError("Snapshot must not be a symlink")
        try:
            snapshot = json.loads(path.read_bytes())
            payload = {k: v for k, v in snapshot.items() if k not in ("id", "sha256")}
            if snapshot.get("id") != snapshot_id or snapshot.get("sha256") != snapshot_id or _digest(_bytes(payload)) != snapshot_id:
                raise HistoryError("Snapshot hash does not match its pinned ID")
            if snapshot.get("schema") != SCHEMA:
                raise HistoryError("Unsupported snapshot schema")
            _validate(snapshot["review"])
            return snapshot
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise HistoryError("Snapshot is unavailable or invalid") from exc

    def list(self, project: str | None = None) -> list[dict]:
        """Return complete pinned records, newest observation first. No writes."""
        snapshots = [self.load(p.stem) for p in self.root.glob("*.json")]
        return sorted((s for s in snapshots if project is None or s["review"]["project"] == project),
                      key=lambda s: (_time(s["review"]["observed_at"]), s["id"]), reverse=True)

    def compare(self, baseline_id: str, current_review: dict,
                history_ids: list[str] | None = None) -> dict:
        """Compare to a fixed snapshot. Historical absence must be proven.

        Explicit history IDs are useful for repeat reviews; omission loads no
        other history. This prevents today's scan from silently moving the base.
        """
        _validate(current_review)
        _revalidate_sources(current_review)
        baseline = self.load(baseline_id)
        old = baseline["review"]
        if old["project"] != current_review["project"]:
            raise HistoryError("Cannot compare different projects")
        if _time(current_review["observed_at"]) < _time(old["observed_at"]):
            raise HistoryError("Current review predates the pinned baseline")
        history = [self.load(i) for i in dict.fromkeys([*(history_ids or []), baseline_id])]
        if any(s["review"]["project"] != old["project"] for s in history):
            raise HistoryError("History belongs to another project")
        history = sorted((s for s in history if _time(s["review"]["observed_at"]) < _time(current_review["observed_at"])),
                         key=lambda s: (_time(s["review"]["observed_at"]), s["id"]))
        before = {f["id"]: f for f in old["findings"]}
        after = {f["id"]: f for f in current_review["findings"]}
        groups = {key: [] for key in ("new", "persisting", "resolved", "recurring", "unchecked")}
        for finding_id in sorted(before.keys() | after.keys()):
            finding = after.get(finding_id) or before[finding_id]
            proofs = []
            if finding_id in before and finding_id in after:
                state = "persisting"
            elif finding_id not in after:
                state = "resolved" if _absence_checked(finding, old, current_review) else "unchecked"
            else:
                state = "new"
            if finding_id in after:
                prior = None
                for snap in history:
                    seen = next((f for f in snap["review"]["findings"] if f["id"] == finding_id), None)
                    if seen:
                        prior = (snap, seen)
                    elif (prior and _time(snap["review"]["observed_at"]) >= _time(old["observed_at"])
                          and _time(prior[0]["review"]["observed_at"]) < _time(snap["review"]["observed_at"])
                          and _absence_checked(prior[1], prior[0]["review"], snap["review"])
                          and _absence_checked(finding, current_review, snap["review"])):
                        state = "recurring"
                        proofs = [prior[0]["id"], snap["id"]]
            refs = [r for s in history for r in s.get("ruling_refs", []) if r["finding_id"] == finding_id]
            groups[state].append({"finding": finding, "finding_id": finding_id, "status": state,
                                  "ruling_refs": refs, "history_snapshot_ids": proofs})
        old_sources = {s["id"]: s for s in old["sources"]}
        new_sources = {s["id"]: s for s in current_review["sources"]}
        changes = []
        for source_id in sorted(old_sources.keys() | new_sources.keys()):
            a, b = old_sources.get(source_id), new_sources.get(source_id)
            if a is None:
                state = "added"
            elif b is None or not a.get("sha256") or not b.get("sha256"):
                state = "unchecked"
            elif a["path"] != b["path"]:
                state = "identity_changed"
            else:
                state = "unchanged" if a["sha256"] == b["sha256"] else "changed"
            changes.append({"source_id": source_id, "status": state,
                            "before": a, "after": b})
        old_checks = {c["id"]: c for c in old["coverage"].get("checks", [])}
        new_checks = {c["id"]: c for c in current_review["coverage"].get("checks", [])}
        coverage_changes = []
        for check_id in sorted(old_checks.keys() | new_checks.keys()):
            a, b = old_checks.get(check_id), new_checks.get(check_id)
            if a != b:
                coverage_changes.append({"check_id": check_id, "before": a, "after": b,
                                         "status": "unchecked" if b is None or b.get("status") != "success" else "changed"})
        return {"schema": "helicon.context-comparison/1", "project": old["project"],
                "baseline_id": baseline_id, "baseline_sha256": baseline["sha256"],
                "baseline_observed_at": old["observed_at"], "observed_at": current_review["observed_at"],
                **groups, "counts": {k: len(v) for k, v in groups.items()}, "sources": changes,
                "coverage_changes": coverage_changes}
