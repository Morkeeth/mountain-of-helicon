import json

from helicon.setup_status import SCHEMA, compare_snapshots, setup_status


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_no_baseline_says_tracking_started_and_claims_no_change(tmp_path):
    write(tmp_path / "AGENTS.md", "Use Python 3.10.\n")
    report = setup_status(home=tmp_path, project=tmp_path,
                          observed_at="2026-09-29T10:00:00+00:00")
    comparison = report["comparison"]
    assert comparison["status"] == "tracking_started"
    assert comparison["baseline_observed_at"] is None
    assert "no change is claimed" in comparison["message"].lower()
    assert comparison["edges"] == {"added": [], "removed": [], "changed": []}


def test_configured_is_not_rounded_up_to_loaded_or_used(tmp_path):
    write(tmp_path / "AGENTS.md", "instructions\n")
    snapshot = setup_status(home=tmp_path, project=tmp_path)["snapshot"]
    edge = next(edge for edge in snapshot["edges"]
                if edge["relation"] == "configured_for")
    assert edge["evidence"] == {
        "configured": "observed", "loaded": "unknown", "used": "unknown"}
    ids = [component["id"] for component in snapshot["components"]]
    assert len(ids) == len(set(ids))


def test_changed_instruction_is_a_changed_edge_against_explicit_snapshot(tmp_path):
    source = write(tmp_path / "AGENTS.md", "first\n")
    before = setup_status(home=tmp_path, project=tmp_path,
                          observed_at="2026-09-28T10:00:00+00:00")["snapshot"]
    source.write_text("second\n")
    current = setup_status(home=tmp_path, project=tmp_path,
                           observed_at="2026-09-29T10:00:00+00:00")["snapshot"]
    comparison = compare_snapshots(current, before)
    assert comparison["status"] == "changed"
    assert len(comparison["edges"]["changed"]) == 2  # Codex and Cursor read AGENTS.md
    changed = comparison["edges"]["changed"][0]
    assert changed["before"]["fingerprint"] != changed["after"]["fingerprint"]


def test_unknown_coverage_is_visible(tmp_path):
    snapshot = setup_status(home=tmp_path, project=tmp_path)["snapshot"]
    assert snapshot["schema"] == SCHEMA
    assert snapshot["coverage"]["status"] == "partial"
    assert "effective model context" in snapshot["coverage"]["unknown"]
    assert "plugin activation" in snapshot["coverage"]["unknown"]


def test_status_json_can_be_used_as_the_next_explicit_baseline(tmp_path):
    write(tmp_path / "AGENTS.md", "same\n")
    first = setup_status(home=tmp_path, project=tmp_path,
                         observed_at="2026-09-28T10:00:00+00:00")
    baseline = tmp_path / "previous.json"
    baseline.write_text(json.dumps(first))
    second = setup_status(home=tmp_path, project=tmp_path, previous=baseline,
                          observed_at="2026-09-29T10:00:00+00:00")
    assert second["comparison"]["status"] == "unchanged"
    assert second["comparison"]["baseline_observed_at"] == first["snapshot"]["observed_at"]
