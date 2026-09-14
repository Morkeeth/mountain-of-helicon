import hashlib
import json

import pytest

from helicon.project_review import project_review


def fixture(root):
    (root / "active-board.json").write_text(json.dumps({"projects": [{"id": "sample", "aliases": ["old-sample"]}]}))
    (root / "zup-next.json").write_text(json.dumps({"queue": []}))
    document = root / "plan.md"
    document.write_text("# Synthetic approved plan\n")
    actor = {"kind": "human", "id": "fixture-reviewer"}
    record = dict(projectID="sample", revision=1, operationID="fixture-save",
                  requestHash="a" * 64, phase="Validate", workStatus="Completed",
                  source="native-project-editor", actor=actor, reason="Correct the phase",
                  observedAt="2026-09-04T20:00:00Z", history=[],
                  documents=[dict(role="Build plan", uri=document.as_uri(),
                    hash=hashlib.sha256(document.read_bytes()).hexdigest(), status="Approved",
                    source="native-project-editor", actor=actor, confirmedAt="2026-09-04T20:00:00Z")])
    store = {"schema": "zup.project-intents/1", "projects": {"sample": record}}
    (root / "project-intents.json").write_text(json.dumps(store))
    return store, document


def test_phase_correction_is_scoped_not_an_outcome(tmp_path):
    fixture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    report = project_review(tmp_path)
    assert report["status"] == "measured"
    assert report["coverage"]["phase_intents"] == 1
    assert report["coverage"]["event_backed"] == 0
    assert report["coverage"]["unverified"] == 0
    row = report["projects"][0]
    assert row["intent"]["phase"] == "Validate"
    assert row["state"] == "phase recorded; outcome not verified"
    assert row["evidence_status"] == "phase-intent"
    assert row["event_id"] is None
    assert before == {p: p.read_bytes() for p in tmp_path.iterdir()}


def test_changed_approved_document_keeps_approval_on_old_bytes(tmp_path):
    _, document = fixture(tmp_path)
    document.write_text("# Different draft\n")
    report = project_review(tmp_path)
    finding = next(f for f in report["findings"] if f["kind"] == "project-document-changed")
    assert finding["document"]["status"] == "Approved"
    assert finding["document"]["expected_hash"] != finding["document"]["current_hash"]
    assert report["coverage"]["phase_intents"] == 1


def test_missing_document_is_explicit(tmp_path):
    _, document = fixture(tmp_path)
    document.unlink()
    report = project_review(tmp_path)
    assert any(f["kind"] == "project-document-unavailable" for f in report["findings"])


@pytest.mark.parametrize("field,value", [("projectID", "other"), ("revision", True),
    ("actor", {"kind": "unknown", "id": "fixture"}), ("source", "generated-guess"),
    ("observedAt", "2099-01-01T00:00:00Z"), ("observedAt", "2026-09-04")])
def test_invalid_provenance_cannot_establish_phase(tmp_path, field, value):
    store, _ = fixture(tmp_path)
    store["projects"]["sample"][field] = value
    (tmp_path / "project-intents.json").write_text(json.dumps(store))
    report = project_review(tmp_path)
    assert report["coverage"]["phase_intents"] == 0
    assert report["coverage"]["unverified"] == 1
    assert any(f["kind"] == "invalid-project-intent" for f in report["findings"])


def test_missing_optional_store_and_malformed_store_are_different(tmp_path):
    fixture(tmp_path)
    intent = tmp_path / "project-intents.json"
    intent.unlink()
    assert project_review(tmp_path)["intent_source"]["status"] == "not_configured"
    intent.write_text("{not-json")
    report = project_review(tmp_path)
    assert report["intent_source"]["status"] == "unavailable"
    assert report["status"] == "attention"
    assert report["project_count"] == 1
    assert any(f["kind"] == "source-unavailable" for f in report["findings"])


def test_phase_correction_cannot_rescue_broken_outcome_receipt(tmp_path):
    fixture(tmp_path)
    board = tmp_path / "active-board.json"
    board.write_text(json.dumps({"projects": [{"id": "sample", "lifecycle": "submitted", "stateEventId": "missing-receipt"}]}))
    report = project_review(tmp_path)
    assert report["coverage"]["phase_intents"] == 0
    assert report["coverage"]["unverified"] == 1
    assert report["projects"][0]["intent"]["phase"] == "Validate"
    assert report["projects"][0]["state"] == "not verified"
    assert any(f["kind"] == "missing-event" for f in report["findings"])


def test_concurrent_document_change_cannot_produce_false_conflict(tmp_path, monkeypatch):
    _, document = fixture(tmp_path)
    original = type(document).read_bytes

    def changing_read(path):
        value = original(path)
        if path == document:
            document.write_text("changed during the check")
        return value

    monkeypatch.setattr(type(document), "read_bytes", changing_read)
    report = project_review(tmp_path)
    assert report["status"] == "unmeasured"
    assert "changed during review" in report["reason"]
    assert report["findings"] == []
    assert report["projects"] == []
