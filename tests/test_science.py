"""Agent Science — the verdict logic is the product, so the tests are on it.

The wedge is a classifier: a published threshold's unit may have one reading or
many, and when many readings straddle the scale the honest verdict is not a guess
but UNMEASURABLE. These pin that rule, then confirm the three seeded thresholds
carry the honesty fields the PRD §7 trap requires (source, date, vendor mark).
"""
import sqlite3

import pytest

from helicon.science import (
    INSIDE, CLEAR, UNMEASURABLE,
    Reading, classify, REGISTRY, THRESHOLD_MEMORY, THRESHOLD_HYBRID,
    THRESHOLD_RAG, interaction_readings, _has_reranker, render,
)


def _r(*values):
    return [Reading(f"reading{i}", v, "SELECT 1") for i, v in enumerate(values)]


# --- classify: the core ------------------------------------------------------

def test_single_reading_below_scale_is_clear():
    assert classify(_r(4_214), 500_000, False) == CLEAR


def test_single_reading_past_scale_without_mitigation_is_inside():
    assert classify(_r(600_000), 500_000, False) == INSIDE


def test_single_reading_past_scale_with_mitigation_is_clear():
    assert classify(_r(600_000), 500_000, True) == CLEAR


def test_all_readings_below_scale_is_clear_despite_ambiguous_unit():
    # every reading of a 5-way-ambiguous unit is below 1M -> ambiguity is moot
    assert classify(_r(28, 547, 4_926, 9_350, 14_961), 1_000_000, None) == CLEAR


def test_readings_straddling_scale_are_unmeasurable():
    # the memory case: four readings below 10K, one above -> cannot say which side
    assert classify(_r(28, 547, 4_926, 9_350, 14_961), 10_000, True) == UNMEASURABLE


def test_all_readings_past_scale_without_mitigation_is_inside():
    assert classify(_r(20_000, 50_000), 10_000, False) == INSIDE


def test_all_readings_past_scale_with_mitigation_is_clear():
    assert classify(_r(20_000, 50_000), 10_000, True) == CLEAR


def test_all_readings_past_scale_mitigation_unknown_is_unmeasurable():
    # cannot assert INSIDE's "lacks the mitigation" when the mitigation is unread
    assert classify(_r(20_000, 50_000), 10_000, None) == UNMEASURABLE


def test_no_readings_is_unmeasurable():
    assert classify([], 10_000, True) == UNMEASURABLE


def test_boundary_value_equal_to_scale_counts_as_past():
    assert classify(_r(10_000), 10_000, False) == INSIDE


# --- registry honesty (PRD §7 trap) -----------------------------------------

def test_all_seeded_thresholds_are_vendor_marked_with_source_and_date():
    assert len(REGISTRY) == 3
    for t in REGISTRY:
        assert t.source and t.source_date
        # all three come from the ranksquire blog, one of the two vendor blogs
        assert t.source_is_vendor is True
        assert t.source_note
        assert callable(t.probe)


def test_the_two_prd_thresholds_are_seeded_verbatim_shape():
    assert THRESHOLD_RAG.scale_it_bites_at == 500_000
    assert THRESHOLD_RAG.scale_unit == "vectors"
    assert THRESHOLD_MEMORY.scale_it_bites_at == 10_000
    assert THRESHOLD_MEMORY.scale_unit == "interactions"


def test_hybrid_claim_stored_as_published_not_inverted():
    # the source claims composition HOLDS reliability; we must not store our
    # inversion ("drops without hybrid") in its mouth
    assert "holds" in THRESHOLD_HYBRID.claim.lower()


def test_reranker_detection_reads_config_offline():
    assert _has_reranker({}) is False
    assert _has_reranker({"embeddings": {"api_key": "k", "base_url": "u"}}) is True
    assert _has_reranker({"embeddings": {"api_key": "k"}}) is False


# --- probes against a synthetic store ---------------------------------------

def _store():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE retrieval_log(id INTEGER);"
        "CREATE TABLE audit_log(id INTEGER, human_decision TEXT);"
        "CREATE TABLE helicon_cubes(id INTEGER, review_status TEXT, merged_into TEXT);"
        "CREATE TABLE reviews(id INTEGER);"
        "CREATE TABLE cube_embeddings(id INTEGER);"
    )
    return conn


def test_interaction_readings_shape_and_reproduce_sql():
    conn = _store()
    conn.execute("INSERT INTO retrieval_log VALUES (1)")
    conn.execute("INSERT INTO audit_log VALUES (1, 'kept')")
    conn.execute("INSERT INTO audit_log VALUES (2, NULL)")  # not a human ruling
    conn.execute("INSERT INTO helicon_cubes VALUES (1, 'approved', NULL)")
    conn.execute("INSERT INTO helicon_cubes VALUES (2, 'killed', NULL)")
    conn.execute("INSERT INTO reviews VALUES (1)")
    readings = interaction_readings(conn)
    by = {r.name: r for r in readings}
    assert by["logged retrievals"].value == 1
    assert by["human rulings on findings"].value == 1  # NULL excluded
    assert by["live memories"].value == 1              # killed excluded
    assert by["all memories ever"].value == 2
    # every reading names the query that produced it
    assert all(r.sql.upper().startswith("SELECT") for r in readings)


def test_memory_probe_is_unmeasurable_when_readings_straddle():
    conn = _store()
    # one reading past 10K, the rest below -> straddle
    conn.executemany("INSERT INTO helicon_cubes VALUES (?, 'killed', NULL)",
                     [(i,) for i in range(11_000)])
    conn.execute("INSERT INTO audit_log VALUES (1, 'kept')")
    res = THRESHOLD_MEMORY.probe(conn, {})
    assert res.verdict == UNMEASURABLE
    assert res.unit_note
    assert len(res.readings) == 5


def test_rag_probe_clear_below_scale_and_renders():
    conn = _store()
    conn.executemany("INSERT INTO cube_embeddings VALUES (?)", [(i,) for i in range(10)])
    res = THRESHOLD_RAG.probe(conn, {})
    assert res.verdict == CLEAR
    out = render(conn, {}, "/tmp/x.db")
    assert "rag-precision-500k" in out and "[vendor]" in out
    assert "UNMEASURABLE" in out  # the memory threshold straddles on any store
