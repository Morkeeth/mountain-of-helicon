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
    assert report["findings"][0]["kind"] == "unscoped-settled-project-request"


def test_wrong_project_receipt_cannot_count_as_event_evidence(tmp_path):
    fixture(tmp_path)
    path = tmp_path / 'project-events/receipt.json'
    event = json.loads(path.read_text())
    event['projectId'] = 'unrelated'
    path.write_text(json.dumps(event))
    report = project_review(tmp_path)
    assert report['coverage']['event_backed'] == 0
    assert report['coverage']['unverified'] == 1
    assert any(f['kind'] == 'projection-disagrees-with-event' for f in report['findings'])


def test_new_decision_is_not_obsolete_just_because_project_submitted(tmp_path):
    fixture(tmp_path)
    path = tmp_path / 'zup-next.json'
    path.write_text(json.dumps({'queue': [{'id': 'readycounter', 'band': 'PARKED', 'needsHuman': True,
        'decision': {'id': 'new-question', 'question': 'Publish the retrospective?',
                     'stateRelation': {'kind': 'independent-question', 'source': 'operator', 'milestoneID': 'retrospective',
                                       'stateEventID': 'receipt', 'confirmedAt': '2026-09-04T21:00:00Z'}}}]}))
    assert project_review(tmp_path)['status'] == 'measured'


def test_independence_must_reference_current_state(tmp_path):
    fixture(tmp_path)
    path = tmp_path / 'zup-next.json'
    path.write_text(json.dumps({'queue': [{'id': 'readycounter', 'band': 'PARKED', 'needsHuman': True,
        'decision': {'stateRelation': {'kind': 'independent-question', 'source': 'operator', 'milestoneID': 'new',
                     'stateEventID': 'wrong-receipt', 'confirmedAt': '2026-09-04T21:00:00Z'}}}]}))
    assert project_review(tmp_path)['findings'][0]['kind'] == 'unscoped-settled-project-request'


def test_read_only_and_scope(tmp_path):
    fixture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    report = project_review(tmp_path)
    assert report["status"] == "measured"
    assert report["event_count"] == 1
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*.json")}


def test_missing_is_not_clean(tmp_path):
    assert project_review(tmp_path)["status"] == "unmeasured"
