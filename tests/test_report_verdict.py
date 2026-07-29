"""The scoreboard's own calibration.

`report.py` had no test file at all, which is most of how it drifted: the
headline verdict for cross-session accuracy could not return HEALTHY under any
input, and nobody noticed because nothing asserted that it could.

The condition was:

    regressed <= 0 and (contra_rate is None or contra_rate >= 0.8)
    and open_pairs == 0

`open_pairs` counts findings awaiting HUMAN triage. Helicon's entire design is a
human review queue, so a live store has a backlog by definition (344 open
findings store-wide, 6 pair findings, at the time this was found). The verdict
therefore read DEGRADED because the system was working as designed, and carried
no information about accuracy at all.

These tests pin the calibration itself:
  1. HEALTHY is reachable — a clean store with a backlog is HEALTHY.
  2. Every number in the verdict expression is a number about ACCURACY.
  3. The worst number in the report (grounding, 0.385) is gated, not decorative.
  4. Unmeasured is DEGRADED, never a silent pass.
"""
import pytest

from helicon.report import THRESHOLDS, cross_session_verdict, format_report


def test_healthy_is_reachable_when_accuracy_is_clean():
    """The regression this file exists for: before the fix, no input to this
    function could return HEALTHY on a store with any review backlog — which is
    every live store."""
    out = cross_session_verdict(regressed=0, snaps_total=13,
                                contra_rate=1.0, grounding_rate=1.0)
    assert out["verdict"] == "HEALTHY"
    assert "all accuracy gates passed" in out["reason"]


def test_backlog_is_not_an_input_to_the_verdict():
    """The signature is the assertion: there is nowhere to pass a backlog count.

    Gating accuracy on queue depth conflated 'the human has not triaged this
    yet' with 'the memory is wrong'. If a future edit reintroduces the term,
    this call stops type-checking and the test fails loudly."""
    with pytest.raises(TypeError):
        cross_session_verdict(0, 13, 1.0, 1.0, open_pairs=6)


def test_grounding_is_gated_not_decorative():
    """0.385 was the worst number in the report, printed on every run, drifting
    0.462 -> 0.538 -> 0.385, and it appeared nowhere in the verdict."""
    out = cross_session_verdict(regressed=0, snaps_total=13,
                                contra_rate=1.0, grounding_rate=0.385)
    assert out["verdict"] == "DEGRADED"
    assert "grounding_pass_rate 0.385" in out["reason"]
    assert "0.8" in out["reason"]  # the threshold it failed, stated inline


def test_regressions_still_fail_the_gate():
    out = cross_session_verdict(regressed=2, snaps_total=13,
                                contra_rate=1.0, grounding_rate=1.0)
    assert out["verdict"] == "DEGRADED"
    assert "snapshot_regressions 2" in out["reason"]


def test_unmeasured_is_degraded_never_a_silent_pass():
    """`contra_rate is None` used to satisfy the condition, so running without
    --llm made the two judged tests vanish and the verdict improve. Same failure
    class as R4's unconfigured code arm reading as CLEAN."""
    out = cross_session_verdict(regressed=0, snaps_total=13,
                                contra_rate=None, grounding_rate=None)
    assert out["verdict"] == "DEGRADED"
    assert "unmeasured, not clean" in out["reason"]
    assert "contradiction_pass_rate" in out["reason"]
    assert "grounding_pass_rate" in out["reason"]
    assert "--llm" in out["reason"]


def test_no_baselines_says_so_rather_than_scoring_zero_regressions():
    """Zero captured snapshots must not read as 'zero regressions'."""
    out = cross_session_verdict(regressed=0, snaps_total=0,
                                contra_rate=1.0, grounding_rate=1.0)
    assert out["verdict"] == "DEGRADED"
    assert "no baselines captured" in out["reason"]


def test_every_gate_carries_its_own_arithmetic():
    """A bare verdict word asks to be trusted. Each gate must publish value,
    threshold, operator and whether it was measured, so a reader can recompute
    the headline by hand."""
    gates = cross_session_verdict(1, 13, 0.9, 0.385)["gates"]
    assert {g["name"] for g in gates} == {
        "snapshot_regressions", "contradiction_pass_rate", "grounding_pass_rate"}
    for g in gates:
        assert set(g) == {"name", "value", "threshold", "op", "measured", "pass"}
    by_name = {g["name"]: g for g in gates}
    assert by_name["grounding_pass_rate"]["threshold"] == \
        THRESHOLDS["grounding_pass_rate_ok"]
    assert by_name["contradiction_pass_rate"]["pass"] is True
    assert by_name["snapshot_regressions"]["pass"] is False


def test_thresholds_are_declared_not_inline():
    """The 0.8 contradiction bar was a magic number inside the expression while
    every other threshold was published in THRESHOLDS and printed with the
    report. A threshold a reader cannot see is not a stated threshold."""
    assert THRESHOLDS["contradiction_pass_rate_ok"] == 0.8
    assert THRESHOLDS["grounding_pass_rate_ok"] == 0.8


def _report_stub(verdict="HEALTHY", reason="all accuracy gates passed") -> dict:
    sub = {"verdict": verdict, "precision_at_3": 0.6, "mrr": 0.6,
           "query_count": 13, "disclosure": "d", "ingest_dedup_rate": 0.1,
           "consolidations": 2, "decay_predicts_human_kills_auc": 0.78,
           "retired_superseded": 1, "retired_killed": 2, "freshness_pass_rate": 1.0,
           "thinness_pass_rate": 1.0, "redundancy_pass_rate": 1.0,
           "mean_tokens_per_query_top5": 900}
    return {
        "track": "MemoryAgent", "overall": verdict,
        "battery_tasks": {"total": 13, "healthy": 13, "degraded": 0, "broken": 0},
        "last_scan_hours_ago": 1, "thresholds": THRESHOLDS,
        "sub_goals": {
            "efficient_storage_retrieval": dict(sub),
            "timely_forgetting": dict(sub),
            "recall_under_limited_context": dict(sub),
            "cross_session_accuracy": {
                "verdict": verdict, "verdict_reason": reason,
                "snapshots_total": 13, "snapshots_regressed": 0,
                "contradiction_pass_rate": 1.0, "grounding_pass_rate": 1.0,
                "llm_judged": True,
                "review_backlog": {"open_pair_findings": 6,
                                   "open_findings_total": 344,
                                   "counts_toward_verdict": False, "note": ""},
                "cross_source_contradictions": {"conflicts_live": 0,
                                                "open_findings": 6,
                                                "sample": None},
            },
        },
    }


def test_the_printed_surface_shows_the_reason_and_separates_backlog():
    out = format_report(_report_stub(
        "DEGRADED", "failed: grounding_pass_rate 0.385 not >= 0.8"))
    assert "why: failed: grounding_pass_rate 0.385 not >= 0.8" in out
    assert "Review backlog (not a verdict input)" in out
    assert "344 open finding(s) store-wide" in out


def test_expired_baselines_are_not_reported_as_none_captured():
    """13 baselines exist on the live store and none are still evidence. Saying
    "no baselines captured" about them would be the same species of wrong this
    module was fixed for: a true-sounding sentence about the wrong fact."""
    out = cross_session_verdict(regressed=0, snaps_total=0, contra_rate=1.0,
                                grounding_rate=1.0, captured=13)
    assert "13 baseline(s) captured but none are still evidence" in out["reason"]
    assert "no baselines captured" not in out["reason"]


def test_a_genuinely_empty_store_still_says_none_captured():
    out = cross_session_verdict(0, 0, 1.0, 1.0, captured=0)
    assert "no baselines captured" in out["reason"]
