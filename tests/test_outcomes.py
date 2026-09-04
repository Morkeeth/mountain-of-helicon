import json
import sqlite3

from helicon.outcomes import outcome_report, compare_cohort


def test_missing_store_is_not_created(tmp_path):
    db = tmp_path / "missing.db"
    assert outcome_report(db)["status"] == "unmeasured"
    assert not db.exists()


def test_attached_and_verified_labels_are_not_accepted_outcomes(tmp_path):
    db = tmp_path / "runs.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE task_runs (id, status, verification_outcome, verification_receipt, human_acceptance, opened_at)")
        assert outcome_report(db)["metrics"]["acceptance_coverage"] is None
        conn.executemany("INSERT INTO task_runs VALUES (?,?,?,?,?,?)", [
            ("one", "artifact_attached", "unverified", None, "pending", "2026-09-01"),
            ("two", "verified", "verified", "{}", None, "2026-09-02"),
            ("three", "reviewed", "verified", json.dumps({"evidence": "test receipt"}), "accepted", "2026-09-03")])
    report = outcome_report(db)
    assert report["metrics"] == dict(recorded_runs=3, verified_with_receipt=1, accepted=1,
                                    rework=0, rollback=0, awaiting_acceptance=2, acceptance_coverage=0.3333)
    assert report["pending_run_ids"] == ["one", "two"]
    assert "test receipt" not in json.dumps(report)


def test_new_runs_do_not_move_the_baseline_denominator():
    baseline = dict(schema="helicon.outcomes/1", source="same", status="measured", observed_at="then",
                    cohort=[dict(id="one", acceptance="pending")])
    current = {**baseline, "cohort": [dict(id="one", acceptance="accepted"), dict(id="two", acceptance="accepted")]}
    result = compare_cohort(baseline, current)
    assert (result["accepted_before"], result["accepted_now"], result["denominator"]) == (0, 1, 1)
    assert result["new_runs_excluded"] == 1
    assert baseline["cohort"][0]["acceptance"] == "pending"
    current["cohort"] = []
    assert compare_cohort(baseline, current)["status"] == "incomplete"
