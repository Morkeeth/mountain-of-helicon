import json
from helicon.project_review import project_review


def test_undated_status_is_a_visible_gap_not_zero_findings(tmp_path):
    (tmp_path / "active-board.json").write_text(json.dumps({"projects": [{"id": "old", "nextHint": "Submit again"}]}))
    (tmp_path / "zup-next.json").write_text(json.dumps({"queue": []}))
    report = project_review(tmp_path)
    assert report["status"] == "attention"
    assert report["coverage"]["unverified"] == 1
    assert report["findings"][0]["kind"] == "undated-project-status"
    assert "current tasks" in report["findings"][0]["consequence"]


def test_dated_ruling_is_not_misreported_as_an_event(tmp_path):
    (tmp_path / "active-board.json").write_text(json.dumps({"projects": [{"id": "p", "stateObservedAt": "2026-09-04T20:00:00Z", "stateEvidence": "operator decision"}]}))
    (tmp_path / "zup-next.json").write_text(json.dumps({"queue": []}))
    report = project_review(tmp_path)
    assert report["coverage"] == {"total": 1, "event_backed": 0, "dated_rulings": 1, "phase_intents": 0, "unverified": 0}
