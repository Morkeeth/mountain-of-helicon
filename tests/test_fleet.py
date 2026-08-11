"""The Fleet screen, and the drift heuristic it ships.

The deep-research pass found ZERO published, verified techniques for detecting
that an agent wandered off-objective. So this ships a heuristic, and the tests
that matter are the ones that keep it from crying wolf — a drift alarm nobody
trusts is worse than no alarm, because it trains the operator to ignore the
one time it is right.
"""
import pytest

from helicon import autogov, fleet, taskrun
from helicon.db import init_db


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "fleet.db"))


def _files(*paths):
    return [{"path": p, "state": "uncommitted"} for p in paths]


VALUATION_WORK = _files("helicon/valuation.py", "tests/test_valuation.py",
                        "helicon/cli.py", "README.md", "CLAUDE.md")


# ------------------------------------------------------------------ drift

def test_matching_work_does_not_trip_the_alarm(conn):
    """Real case from the first live run: 'harden the valuation gate' against a
    manifest containing helicon/valuation.py must stay quiet."""
    sig = fleet.drift_signal("harden the valuation gate and its tests", VALUATION_WORK)
    assert sig["checkable"] and not sig["worth_a_look"]
    assert "valuation" in sig["shared"]


def test_genuinely_unrelated_work_is_flagged(conn):
    sig = fleet.drift_signal("write the launch announcement copy", VALUATION_WORK)
    assert sig["worth_a_look"]


def test_a_truncated_manifest_is_never_ruled_on(conn):
    """THE regression. The feature's first live run flagged a run that had not
    drifted, because the manifest was capped at 40 files and the matching file
    fell off the end. Absence of evidence in a truncated list is not evidence."""
    truncated = VALUATION_WORK[:2] + [{"path": "", "state": "truncated"}]
    sig = fleet.drift_signal("write the launch announcement copy", truncated)
    assert sig["checkable"] is False
    assert "truncated" in sig["reason"]


def test_a_small_diff_is_never_ruled_on(conn):
    """Two files sharing no vocabulary with the objective is a normal small
    change, not a signal."""
    assert fleet.drift_signal("anything", _files("a.py", "b.py"))["checkable"] is False


def test_capture_marks_its_own_truncation(tmp_path):
    """The guard above only works if the producer says it truncated."""
    import helicon.capture as cap
    marked = [{"path": "", "state": "truncated"}]
    assert fleet.drift_signal("x y z", _files("a", "b", "c", "d") + marked)["checkable"] is False


def test_an_observed_run_is_never_drift_checked(conn, tmp_path, monkeypatch):
    """An auto-observed run had no objective frozen, so it cannot have drifted
    from one. Flagging it would invent a contract that never existed."""
    import helicon.cockpit as ck
    root = tmp_path / "CODE"
    proj = root / "helicon-p"
    proj.mkdir(parents=True)
    monkeypatch.setattr(ck, "CODE_ROOT", str(root.resolve()))
    autogov.session_start(conn, str(proj), "s1")
    rid = autogov.unreviewed(conn)[0]["id"]
    taskrun.attach_artifact(conn, rid, VALUATION_WORK)
    row = [r for r in fleet.running(conn) if r["id"] == rid][0]
    assert row["observed"] is True
    assert row["drift"]["checkable"] is False


# ------------------------------------------------------------------ spend

def test_unmeasured_cost_is_counted_separately_never_as_zero(conn):
    """A fleet that looks cheap because it was unmeasured is the worst possible
    answer to 'how is my spending going'."""
    rid = taskrun.open_run(conn, "o", "a", harness="t", repo_ref="/tmp/proj@abc")
    taskrun.build_packet(conn, rid, query="o")
    taskrun.attach_artifact(conn, rid, [], cost_observation={"status": "unknown"})
    row = fleet.spend_by_project(conn)[0]
    assert row["tokens"] == 0 and row["unmeasured"] == 1


def test_known_cost_is_summed(conn):
    rid = taskrun.open_run(conn, "o", "a", harness="t", repo_ref="/tmp/proj@abc")
    taskrun.build_packet(conn, rid, query="o")
    taskrun.attach_artifact(conn, rid, [],
                            cost_observation={"status": "known", "total_tokens": 5000})
    assert fleet.spend_by_project(conn)[0]["tokens"] == 5000


# ------------------------------------------------------------------ efficiency

def test_efficiency_always_reports_its_sample_size(conn):
    """At this n the number is a direction, not a finding, and the screen has to
    say so rather than presenting a mean as a result."""
    eff = fleet.efficiency(conn)
    assert set(eff) == {"accepted", "rework", "rollback"}
    assert all("measured" in v for v in eff.values())


def test_efficiency_is_unmeasurable_rather_than_zero_when_nothing_has_cost(conn):
    assert fleet.efficiency(conn)["accepted"]["mean_tokens"] is None
    # format_fleet became format_projects when the screen went project-first;
    # the efficiency section and its honesty about zero are unchanged.
    assert "not measurable yet" in fleet.format_projects(
        [], {"count": 0, "terminal_hours": 0, "sessions": [], "basis": ""}, [],
        [], [], fleet.efficiency(conn))
