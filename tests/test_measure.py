"""The measurement store.

A reading is a number someone looked at once; a measurement is a number with a
previous value. These tests are mostly about the difference — and about the three
ways a series can lie: a gap drawn as a zero, a first reading drawn as a trend,
and one week read four times drawn as four weeks.
"""
from datetime import datetime

import pytest

from helicon.db import init_db
from helicon.measure import (LABELS, RETIRED, RULES, STACK_TARGET, Metric,
                             record, render_series, retire, series)


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "h.db"))


def _m(key, value, pop=None, unmeasured=""):
    return Metric(key, value, f"cmd for {key}", population=pop,
                  unmeasured=unmeasured)


def test_a_first_reading_has_no_delta(conn):
    """A delta implies a previous value. Rendering 0 would claim the number held
    steady across a week nobody measured."""
    record(conn, [_m("outward", 2)], now=datetime(2026, 8, 16))
    m = series(conn)["metrics"][0]
    assert m["latest"] == 2 and m["delta"] is None and m["readings"] == 1
    assert "first reading" in render_series(series(conn))


def test_a_second_reading_is_where_the_delta_appears(conn):
    record(conn, [_m("outward", 2)], now=datetime(2026, 8, 16))   # W33
    record(conn, [_m("outward", 5)], now=datetime(2026, 8, 23))   # W34
    m = series(conn)["metrics"][0]
    assert m["delta"] == 3 and m["readings"] == 2


def test_one_week_read_four_times_is_still_one_week(conn):
    """Re-recording inside a week REPLACES that week. Appending would draw four
    weeks of trend from one day of glances — the fake-precision defect the
    detectors this records were built to catch."""
    for v in (1, 2, 3, 4):
        record(conn, [_m("outward", v)], now=datetime(2026, 8, 16))
    data = series(conn)
    assert data["weeks"] == ["2026-W33"]
    m = data["metrics"][0]
    assert m["readings"] == 1 and m["latest"] == 4 and m["delta"] is None


def test_an_unmeasured_metric_is_null_never_zero(conn):
    """Storing 0 for a detector that could not run draws a falling line and reads
    as improvement."""
    record(conn, [_m("outward", None, unmeasured="no lane ledger configured")],
           now=datetime(2026, 8, 16))
    m = series(conn)["metrics"][0]
    assert m["latest"] is None
    assert m["points"][0]["value"] is None
    card = render_series(series(conn))
    assert "unmeasured" in card and "no lane ledger configured" in card


def test_a_gap_week_does_not_become_a_change(conn):
    """An unmeasured week between two real ones is a gap, not a movement. The
    delta compares the two REAL readings rather than treating the gap as zero."""
    record(conn, [_m("outward", 2)], now=datetime(2026, 8, 16))
    record(conn, [_m("outward", None, unmeasured="not configured")],
           now=datetime(2026, 8, 23))
    record(conn, [_m("outward", 4)], now=datetime(2026, 8, 30))
    m = series(conn)["metrics"][0]
    assert m["delta"] == 2, "compared the two measured readings, not the gap"


def test_nothing_recorded_renders_as_nothing_recorded(conn):
    card = render_series(series(conn))
    assert "nothing recorded yet" in card.lower()
    assert "helicon measure --record" in card


def test_a_withdrawn_metric_is_deleted_not_left_flat(conn):
    """A metric that stops being collected would otherwise sit at its last value
    forever, which reads as a flat line rather than as a metric withdrawn."""
    key = sorted(RETIRED)[0]
    record(conn, [_m(key, 9), _m("outward", 2)], now=datetime(2026, 8, 16))
    assert len(series(conn)["metrics"]) == 2
    removed = retire(conn)
    assert removed.get(key) == 1
    assert [m["metric"] for m in series(conn)["metrics"]] == ["outward"]


def test_every_shipped_metric_cites_a_doctrine_rule():
    """The citation IS the opinionated part. A KPI with no rule behind it is the
    hygiene-count failure this set replaced."""
    assert set(LABELS) == set(RULES), "a labelled metric with no rule, or vice versa"
    for key, (rule, why) in RULES.items():
        assert rule and why, f"{key} cites nothing"


def test_a_retired_metric_is_never_also_a_shipped_one():
    assert not (set(RETIRED) & set(LABELS)), "a metric cannot be both live and withdrawn"


def test_the_target_names_its_own_provenance():
    """A doctrine document is a claim with an author. The target says which one
    and when, so a model upgrade that changes the doctrine can bump it."""
    assert STACK_TARGET["version"] and STACK_TARGET["date"]
    assert "agentic-engineering-stack-and-taste" in STACK_TARGET["derived_from"]
    assert STACK_TARGET["judgment_not_graded"], \
        "doctrine that cannot be probed must be listed, not silently dropped"


def test_ungradeable_doctrine_is_declared_rather_than_forced_into_a_number():
    joined = " ".join(STACK_TARGET["judgment_not_graded"]).lower()
    assert "self-reported" in joined, \
        "the RECEIPT-blocked metrics must say why they are not shipped"
