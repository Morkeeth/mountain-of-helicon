"""Guarded retrieve: the read side of the ruling engine.

Proves that after a human rules the Stripe contradiction, a later retrieval about
Stripe returns the ruled-true answer AND holds back the memory that still asserts the
ruled-wrong value — the mirror of the write-time guard.
"""
import json
import os
import sqlite3

import pytest


@pytest.fixture
def ruled_demo(tmp_path):
    """A seeded demo store with the full schema and the Stripe finding already ruled
    'live — real money'. The ruling is applied directly (human_decision='resolved:...')
    — exactly what _load_factual_resolutions reads — so the fixture is hermetic and does
    not depend on the app's cached config."""
    from helicon import demo
    from helicon.db import init_db

    db = str(tmp_path / "guarded.db")
    demo.seed(db)
    init_db(db)  # idempotent: adds the full schema (memory_utility etc.) the retriever needs

    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE audit_log SET human_decision='resolved:live — real money', "
        "resolved_at='2026-07-19T20:00:00' WHERE target_id='demo-stripe-live'"
    )
    conn.commit()
    return db


def _conn(db):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return c


def test_trusted_answer_is_the_ruled_value(ruled_demo):
    from helicon.retrieve_guard import guarded_context

    res = guarded_context(_conn(ruled_demo), "Is Stripe safe to run a checkout against?")
    topics = {t["topic"]: t for t in res["trusted_answer"]}
    assert "Stripe" in topics, "the ruling about Stripe should surface as the trusted answer"
    assert topics["Stripe"]["answer"] == "live — real money"
    assert "test mode" in topics["Stripe"]["ruled_wrong"]


def test_ruled_wrong_memory_is_flagged_not_served(ruled_demo):
    from helicon.retrieve_guard import guarded_context

    res = guarded_context(_conn(ruled_demo), "What is the current Stripe mode for checkout?")
    # the memory still asserting "test mode" must be held back, never in safe_context
    flagged_text = " ".join(
        f"{m.get('title','')} {m.get('content_preview','')}".lower()
        for m in res["flagged_context"]
    )
    safe_text = " ".join(
        f"{m.get('title','')} {m.get('content_preview','')}".lower()
        for m in res["safe_context"]
    )
    assert res["suppressed_count"] >= 1
    assert "test mode" in flagged_text
    assert "safe to run a checkout" not in safe_text  # the dangerous fragment is not served as safe


def test_read_only_no_ruling_mutation(ruled_demo):
    """Guarded retrieve must not change any ruling or memory."""
    from helicon.retrieve_guard import guarded_context

    before = _conn(ruled_demo).execute(
        "SELECT human_decision FROM audit_log WHERE target_id='demo-stripe-live'"
    ).fetchone()[0]
    guarded_context(_conn(ruled_demo), "Stripe checkout mode")
    after = _conn(ruled_demo).execute(
        "SELECT human_decision FROM audit_log WHERE target_id='demo-stripe-live'"
    ).fetchone()[0]
    assert before == after
