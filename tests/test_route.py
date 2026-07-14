"""helicon route - the routing read of the eval store.

Hermetic: no real repos, no git, no network. Evidence rows are inserted directly
so the ranking + honesty rules are what's under test. The invariants that matter:
Wilson discounts small samples, unverified never counts as a fail, and a
below-threshold class returns 'insufficient evidence', never a fabricated pick.
"""
import pytest

from helicon.db import init_db
from helicon.route import (
    normalize_model, harness_of, wilson_lower, TASK_CLASS_OF_KIND, route)


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "h.db"))


_SEQ = [0]


def _ev(conn, model, task_class, verdict, harness="claude-code", key=None):
    _SEQ[0] += 1
    key = key or f"k{_SEQ[0]}"
    conn.execute(
        "INSERT INTO route_evidence "
        "(model,harness,task_class,verdict,terminal,repo,claim,receipt,created_at,pair_key) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (model, harness, task_class, verdict, "T", "/r", "c", "rcpt", "2026-07-20", key))
    conn.commit()


# --- attribution parsing ----------------------------------------------------

def test_normalize_model_strips_vendor_and_email():
    assert normalize_model("Claude Opus 4.8 (1M context) <noreply@anthropic.com>") \
        == "Opus 4.8 (1M context)"
    assert normalize_model("Claude Fable 5 <noreply@anthropic.com>") == "Fable 5"
    assert normalize_model("") == "unknown"


def test_harness_inference_from_signature():
    assert harness_of("Claude Opus 4.8 <noreply@anthropic.com>") == "claude-code"
    assert harness_of("Cursor Agent <agent@cursor.sh>") == "cursor"
    assert harness_of("some random person <x@y.com>") == "unknown"


def test_task_class_mapping_covers_review_kinds():
    assert TASK_CLASS_OF_KIND["test"] == "testing"
    assert TASK_CLASS_OF_KIND["ship"] == "delivery"
    assert TASK_CLASS_OF_KIND["endpoint"] == "api-surface"


# --- Wilson: the anti-fabrication ranking key -------------------------------

def test_wilson_discounts_small_samples():
    # a perfect 1/1 must NOT outrank a strong 9/10 - that's the whole point
    assert wilson_lower(1, 1) < wilson_lower(9, 10)
    assert wilson_lower(0, 0) == 0.0
    # more evidence at the same rate raises the lower bound (confidence grows)
    assert wilson_lower(50, 100) > wilson_lower(5, 10)


# --- route(): honesty rules -------------------------------------------------

def test_insufficient_evidence_below_threshold(conn):
    _ev(conn, "Opus 4.8", "testing", "verified")
    _ev(conn, "Opus 4.8", "testing", "verified")
    r = route(conn, min_n=5)["results"]
    assert len(r) == 1
    assert r[0]["sufficient"] is False
    assert r[0]["recommendation"] is None       # never a fabricated pick
    assert r[0]["best"]["n"] == 2


def test_unverified_is_excluded_not_a_fail(conn):
    for _ in range(6):
        _ev(conn, "Opus 4.8", "testing", "verified")
    for _ in range(4):
        _ev(conn, "Opus 4.8", "testing", "unverified")   # uncheckable, not fail
    res = route(conn, min_n=5)["results"][0]
    assert res["best"]["n"] == 6                 # unverified NOT in denominator
    assert res["best"]["pass"] == 6
    assert res["best"]["rate"] == 1.0
    assert res["uncheckable"] == 4               # surfaced, but never counted as fail


def test_ranks_models_by_wilson_and_makes_a_pick(conn):
    # model A: 10/10 ; model B: 3/3 -> A wins on Wilson despite equal raw rate
    for _ in range(10):
        _ev(conn, "Opus 4.8", "delivery", "verified")
    for _ in range(3):
        _ev(conn, "Fable 5", "delivery", "verified")
    res = route(conn, task_class="delivery", min_n=5)["results"][0]
    assert res["sufficient"] is True
    assert res["recommendation"] == "Opus 4.8"
    assert res["models_compared"] == 2
    assert res["best"]["wilson_lb"] >= res["candidates"][1]["wilson_lb"]


def test_contradicted_lowers_the_rate(conn):
    for _ in range(5):
        _ev(conn, "Opus 4.8", "api-surface", "verified")
    for _ in range(5):
        _ev(conn, "Opus 4.8", "api-surface", "contradicted")
    res = route(conn, min_n=5)["results"][0]
    assert res["best"]["n"] == 10
    assert res["best"]["pass"] == 5
    assert res["best"]["rate"] == 0.5


def test_provisional_lean_below_threshold_but_positive(conn):
    # 2/2 verified: below n>=5 so NOT a firm recommendation, but a labeled lean
    _ev(conn, "Opus 4.8", "api-surface", "verified")
    _ev(conn, "Opus 4.8", "api-surface", "verified")
    res = route(conn, min_n=5)["results"][0]
    assert res["sufficient"] is False
    assert res["recommendation"] is None          # never a firm pick below threshold
    assert res["lean"] == "Opus 4.8"              # but a directional, sample-aware lean
    # a coin-flip does NOT earn a lean
    _ev(conn, "Fable 5", "testing", "verified")
    _ev(conn, "Fable 5", "testing", "contradicted")
    testing = [r for r in route(conn, min_n=5)["results"] if r["task_class"] == "testing"][0]
    assert testing["lean"] is None


def test_empty_store_returns_no_results(conn):
    routed = route(conn, min_n=5)
    assert routed["total_classes"] == 0
    assert routed["results"] == []
