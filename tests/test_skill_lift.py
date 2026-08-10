"""Lift: does a skill make real work better? An empty store reports CLEAN, not healthy."""
import pytest

from helicon.db import init_db
from helicon.wager import (LIFT_MIN_RUNS_PER_ARM, open_wager, link_wager_to_run,
                           review_declared_skill, skill_lift, render_skill_lift)
import helicon.taskrun as taskrun


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "helicon.db"))


def _run_with_card(conn, *, skill, used, verified_ratio, tokens, idx):
    run_id = taskrun.open_run(conn, f"objective {idx}", "acceptance", task_class="feature",
                              skill_versions=[skill] if used else [])
    card_id = f"run-2026-08-10T{idx:02d}:00"
    conn.execute("UPDATE task_runs SET run_id=? WHERE id=?", (card_id, run_id))
    conn.execute(
        "INSERT INTO run_cards (run_id, verified_ratio, output_tokens, cost, scored_at) "
        "VALUES (?,?,?,?,datetime('now'))", (card_id, verified_ratio, tokens, 0.1))
    wager_id = open_wager(conn, intent=f"i{idx}", beneficiary="operator",
                          observable_change="c", evidence_contract="e",
                          kill_condition="k", task_run_id=run_id)
    if used:
        review_declared_skill(conn, wager_id, skill_version=skill, source_path=__file__)
    conn.commit()
    return wager_id


def test_an_empty_store_is_insufficient_not_zero(conn):
    report = skill_lift(conn, "stranger")
    assert report["verdict"] == "insufficient"
    assert report["with_runs"] == 0 and report["without_runs"] == 0
    # The refusal must never render a lift number the data cannot support.
    text = render_skill_lift(report)
    assert "insufficient" in text and "CLEAN, not healthy" in text
    assert "lift" not in text.split("\n")[2].lower()


def test_one_arm_short_of_the_floor_still_refuses(conn):
    for i in range(LIFT_MIN_RUNS_PER_ARM):
        _run_with_card(conn, skill="stranger", used=True, verified_ratio=0.9, tokens=100, idx=i)
    _run_with_card(conn, skill="stranger", used=False, verified_ratio=0.5, tokens=90,
                   idx=LIFT_MIN_RUNS_PER_ARM)
    report = skill_lift(conn, "stranger")
    assert report["verdict"] == "insufficient"
    assert report["with_runs"] == LIFT_MIN_RUNS_PER_ARM and report["without_runs"] == 1


def test_both_arms_at_the_floor_produce_a_real_lift(conn):
    idx = 0
    for _ in range(LIFT_MIN_RUNS_PER_ARM):
        _run_with_card(conn, skill="stranger", used=True, verified_ratio=0.9, tokens=120, idx=idx); idx += 1
    for _ in range(LIFT_MIN_RUNS_PER_ARM):
        _run_with_card(conn, skill="stranger", used=False, verified_ratio=0.7, tokens=100, idx=idx); idx += 1
    report = skill_lift(conn, "stranger")
    assert report["verdict"] == "measured"
    assert report["verified_ratio"]["lift"] == pytest.approx(0.2)
    assert report["output_tokens"]["lift"] == pytest.approx(20.0)
    assert "lift" in render_skill_lift(report)


def test_runs_without_the_key_are_excluded_not_guessed(conn):
    """A run captured before task_runs.run_id existed has no cost card. It is
    counted and named, never joined by a time window."""
    run_id = taskrun.open_run(conn, "legacy", "acceptance", task_class="feature")
    open_wager(conn, intent="legacy", beneficiary="operator", observable_change="c",
               evidence_contract="e", kill_condition="k", task_run_id=run_id)
    conn.commit()
    report = skill_lift(conn, "stranger")
    assert report["unjoinable_runs"] == 1
    assert report["with_runs"] == 0
    assert "cannot be joined" in report["reason"]
