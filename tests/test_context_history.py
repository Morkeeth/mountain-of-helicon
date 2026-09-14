"""Repeat-review journeys using real source files and immutable disk snapshots."""

from copy import deepcopy
import hashlib
import json
import os
import subprocess
import sys

import pytest

from helicon.context_history import ContextHistory, HistoryError


def review(path, day=1, finding=True, status="success", text="Use old command.\n"):
    path.write_text(text)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    source = {"id": "instructions", "path": str(path), "sha256": sha,
              "status": "available", "mtime": path.stat().st_mtime}
    return {"schema": "helicon.context-review/1", "project": str(path.parent),
            "observed_at": f"2026-09-{day:02d}T01:00:00+00:00", "sources": [source],
            "findings": [{"id": "wrong-command", "kind": "command", "check_id": "commands",
                          "title": "Wrong command", "consequence": "Agent runs an old command",
                          "action": "Correct the instruction", "evidence": [{"source_id": source["id"],
                          "path": str(path), "sha256": sha, "quote": text}]}] if finding else [],
            "coverage": {"checks": [{"id": "commands", "version": "1", "status": status,
                                      "source_ids": ["instructions"]}]}}


def test_explicit_save_is_immutable_and_reads_never_create_storage(tmp_path):
    store = ContextHistory(tmp_path / "history")
    assert store.list() == []
    assert not store.root.exists()
    r = review(tmp_path / "AGENTS.md")
    snap = store.save(r)
    snapshot_path = store.root / (snap["id"] + ".json")
    pinned_bytes = snapshot_path.read_bytes()
    pinned_mtime = snapshot_path.stat().st_mtime_ns
    assert store.save(r)["id"] == snap["id"]
    r["findings"].clear()
    assert store.load(snap["id"])["review"]["findings"]
    assert snapshot_path.read_bytes() == pinned_bytes
    assert snapshot_path.stat().st_mtime_ns == pinned_mtime
    assert snapshot_path.stat().st_mode & 0o077 == 0


def test_source_changed_or_disappeared_refuses_save_before_creating_storage(tmp_path):
    path = tmp_path / "AGENTS.md"
    store = ContextHistory(tmp_path / "history")
    r = review(path)
    path.write_text("Changed during review")
    with pytest.raises(HistoryError, match="changed"):
        store.save(r)
    assert not store.root.exists()
    path.unlink()
    with pytest.raises(HistoryError, match="unavailable"):
        store.save(r)


def test_tampering_and_path_escape_cannot_be_read_or_overwritten(tmp_path):
    store = ContextHistory(tmp_path / "history")
    r = review(tmp_path / "AGENTS.md")
    snap = store.save(r)
    path = store.root / (snap["id"] + ".json")
    data = json.loads(path.read_text())
    data["review"]["findings"].clear()
    path.write_text(json.dumps(data))
    with pytest.raises(HistoryError, match="hash"):
        store.load(snap["id"])
    with pytest.raises(HistoryError, match="hash"):
        store.save(r)
    with pytest.raises(HistoryError, match="Invalid snapshot ID"):
        store.load("../../AGENTS.md")


def test_resolution_requires_same_successful_check_and_source_population(tmp_path):
    path = tmp_path / "AGENTS.md"
    store = ContextHistory(tmp_path / "history")
    before = store.save(review(path))
    after = review(path, 2, finding=False, text="Use the current command.\n")
    result = store.compare(before["id"], after)
    assert result["counts"]["resolved"] == 1
    assert result["sources"][0]["status"] == "changed"
    assert store.load(before["id"])["review"]["findings"][0]["evidence"][0]["quote"] == "Use old command.\n"
    for mutation in ("unknown", "failed", "missing", "version", "population"):
        candidate = deepcopy(after)
        check = candidate["coverage"]["checks"][0]
        if mutation == "missing":
            candidate["coverage"]["checks"] = []
        elif mutation == "version":
            check["version"] = "2"
        elif mutation == "population":
            check["source_ids"] = []
        else:
            check["status"] = mutation
        diff = store.compare(before["id"], candidate)
        assert diff["counts"]["resolved"] == 0, mutation
        assert diff["counts"]["unchecked"] == 1, mutation


def test_same_bytes_later_scan_is_not_source_change(tmp_path):
    path = tmp_path / "AGENTS.md"
    store = ContextHistory(tmp_path / "history")
    before = store.save(review(path))
    after = review(path, 2)
    result = store.compare(before["id"], after)
    assert result["counts"]["persisting"] == 1
    assert result["sources"][0]["status"] == "unchanged"
    assert result["baseline_observed_at"] != result["observed_at"]


def test_recurring_rejected_claim_requires_proven_absence(tmp_path):
    path = tmp_path / "AGENTS.md"
    store = ContextHistory(tmp_path / "history")
    first = store.save(review(path), [{"finding_id": "wrong-command", "ref": "ruling:17", "verdict": "rejected"}])
    missing = store.save(review(path, 2, finding=False, status="unknown"))
    current = review(path, 3)
    assert store.compare(missing["id"], current, [first["id"]])["counts"]["recurring"] == 0
    assert store.compare(missing["id"], current, [first["id"]])["new"][0]["ruling_refs"][0]["ref"] == "ruling:17"
    clear = store.save(review(path, 2, finding=False, text="Use the current command.\n"))
    current = review(path, 3)
    result = store.compare(clear["id"], current, [first["id"]])
    assert result["counts"]["recurring"] == 1
    assert result["recurring"][0]["history_snapshot_ids"] == [first["id"], clear["id"]]
    assert store.compare(first["id"], current, [clear["id"]])["counts"]["recurring"] == 1
    # A clean snapshot existing elsewhere never silently becomes the baseline.
    assert store.compare(first["id"], current)["counts"]["persisting"] == 1


def test_missing_sources_and_dropped_findings_stay_unchecked(tmp_path):
    path = tmp_path / "AGENTS.md"
    store = ContextHistory(tmp_path / "history")
    before = store.save(review(path))
    after = review(path, 2, finding=False)
    path.unlink()
    after["sources"][0].update(status="missing", sha256=None)
    snap = store.save(after)
    assert snap["source_validation"][0]["status"] == "still_missing"
    assert store.compare(before["id"], after)["counts"]["unchecked"] == 1
    path.write_text("Reappeared")
    with pytest.raises(HistoryError, match="now exists"):
        store.save(after)


def test_wrong_evidence_binding_and_duplicate_ids_rejected(tmp_path):
    r = review(tmp_path / "AGENTS.md")
    store = ContextHistory(tmp_path / "history")
    broken = deepcopy(r)
    broken["findings"][0]["evidence"][0]["sha256"] = "0" * 64
    with pytest.raises(HistoryError, match="exact source"):
        store.save(broken)
    broken = deepcopy(r)
    broken["sources"].append(broken["sources"][0])
    with pytest.raises(HistoryError, match="Duplicate"):
        store.save(broken)


def test_project_and_time_boundaries(tmp_path):
    path = tmp_path / "AGENTS.md"
    store = ContextHistory(tmp_path / "history")
    before = store.save(review(path, 2))
    with pytest.raises(HistoryError, match="predates"):
        store.compare(before["id"], review(path, 1))
    after = review(path, 3)
    after["project"] = "/another-project"
    with pytest.raises(HistoryError, match="different projects"):
        store.compare(before["id"], after)


def test_different_subject_is_new_not_recurring(tmp_path):
    path = tmp_path / "AGENTS.md"
    store = ContextHistory(tmp_path / "history")
    first = store.save(review(path))
    clear = store.save(review(path, 2, finding=False))
    after = review(path, 3)
    after["findings"][0]["id"] = "different-subject-same-command"
    diff = store.compare(clear["id"], after, [first["id"]])
    assert diff["counts"]["new"] == 1
    assert diff["counts"]["recurring"] == 0


def test_compare_does_not_resolve_a_review_that_changed_after_scan(tmp_path):
    path = tmp_path / "AGENTS.md"
    store = ContextHistory(tmp_path / "history")
    first = store.save(review(path))
    after = review(path, 2, finding=False)
    path.write_text("Changed after scan")
    with pytest.raises(HistoryError, match="changed"):
        store.compare(first["id"], after)


def test_same_timestamp_conflicting_scans_do_not_prove_recurrence(tmp_path):
    path = tmp_path / "AGENTS.md"
    store = ContextHistory(tmp_path / "history")
    first = store.save(review(path, 1))
    before = store.save(review(path, 2))
    ambiguous = store.save(review(path, 2, finding=False))
    current = review(path, 3)
    diff = store.compare(before["id"], current, [first["id"], ambiguous["id"]])
    assert diff["counts"]["recurring"] == 0
    assert diff["counts"]["persisting"] == 1


def test_stably_missing_optional_entrypoint_does_not_hide_checked_resolution(tmp_path):
    path = tmp_path / "AGENTS.md"
    store = ContextHistory(tmp_path / "history")
    before = review(path)
    optional = {"id": "optional", "path": str(tmp_path / "CLAUDE.md"), "status": "missing", "sha256": None}
    before["sources"].append(optional)
    before["coverage"]["checks"][0]["source_ids"].append("optional")
    snap = store.save(before)
    after = review(path, 2, finding=False)
    after["sources"].append(optional)
    after["coverage"]["checks"][0]["source_ids"].append("optional")
    assert store.compare(snap["id"], after)["counts"]["resolved"] == 1
    after["sources"][-1] = dict(optional, status="unreadable")
    assert store.compare(snap["id"], after)["counts"]["unchecked"] == 1


def test_source_swap_to_fifo_is_denied_without_blocking(tmp_path):
    path = tmp_path / "AGENTS.md"
    r = review(path)
    path.unlink()
    os.mkfifo(path)
    script = "import json,sys; from helicon.context_history import ContextHistory; ContextHistory(sys.argv[1]).save(json.loads(sys.argv[2]))"
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path / "history"), json.dumps(r)],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert "bounded regular file" in result.stderr
    assert not (tmp_path / "history").exists()


def test_same_bytes_symlink_swap_and_oversized_source_are_denied(tmp_path):
    from helicon.context_history import MAX_SOURCE_BYTES, read_source_bytes
    path = tmp_path / "AGENTS.md"
    r = review(path)
    target = tmp_path / "other.md"
    path.rename(target)
    path.symlink_to(target)
    with pytest.raises(HistoryError, match="symlink"):
        ContextHistory(tmp_path / "history").save(r)
    oversized = tmp_path / "oversized"
    with oversized.open("wb") as stream:
        stream.truncate(MAX_SOURCE_BYTES + 1)
    with pytest.raises(HistoryError, match="bounded regular file"):
        read_source_bytes(oversized)
