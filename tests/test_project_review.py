import json
from helicon.project_review import project_review


def fixture(root, needs_human=False):
    (root / "project-events").mkdir()
    event = dict(schema="zup.project-event/1", id="receipt", projectId="readycounter", type="submitted",
                 evidence="Operator confirmed submission", source="operator", observedAt="2026-09-04T20:00:00Z")
    (root / "project-events/receipt.json").write_text(json.dumps(event))
    (root / "active-board.json").write_text(json.dumps(dict(projects=[dict(id="readycounter", aliases=["duet-webmcp"],
        lifecycle="submitted", stateEventId="receipt", stateEvidence=event["evidence"])])))
    (root / "zup-next.json").write_text(json.dumps(dict(queue=[dict(id="readycounter", needsHuman=needs_human, band="PARKED")])))


def test_actual_queue_contradiction_fires(tmp_path):
    fixture(tmp_path, True)
    report = project_review(tmp_path)
    assert report["status"] == "attention"
    assert report["findings"][0]["kind"] == "settled-project-reopened-in-queue"


def test_read_only_and_scope(tmp_path):
    fixture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    report = project_review(tmp_path)
    assert report["status"] == "measured"
    assert report["event_count"] == 1
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*.json")}


def test_missing_is_not_clean(tmp_path):
    assert project_review(tmp_path)["status"] == "unmeasured"
