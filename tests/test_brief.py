"""The morning brief — all five pillars in one honest object.

Proves the brief assembles every pillar, surfaces the open exception as work worth a
human's judgment, degrades honestly on a store with no signal (never a fabricated
number), and is read-only.
"""
import sqlite3

import pytest


@pytest.fixture
def demo_db(tmp_path):
    from helicon import demo
    from helicon.db import init_db

    db = str(tmp_path / "brief.db")
    demo.seed(db)
    init_db(db)
    return db


def _conn(db):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return c


def test_brief_has_all_five_pillars(demo_db):
    from helicon.brief import build_brief

    b = build_brief(_conn(demo_db))
    assert set(b) == {"truth", "continuity", "direction", "reflection", "calm"}
    for pillar in b.values():
        assert pillar.get("headline"), "every pillar states a headline, even when empty"


def test_open_exception_surfaces_as_worth_your_judgment(demo_db):
    """The demo's Stripe contradiction is critical + unruled — it must reach Calm."""
    from helicon.brief import build_brief

    b = build_brief(_conn(demo_db))
    assert b["calm"]["open_exceptions"] >= 1
    stripe = [e for e in b["calm"]["worth_your_judgment"] if e["severity"] == "critical"]
    assert stripe, "the critical Stripe finding should be flagged for a ruling"


def test_empty_signals_degrade_honestly_not_fabricated(demo_db):
    """A pillar with no data says so; a pillar with data gives a REAL answer."""
    from helicon.brief import build_brief

    b = build_brief(_conn(demo_db))
    # continuity has no context packets on the seed -> say so, don't invent
    assert b["continuity"]["context_packets"] == 0
    assert "Nothing carried between runs" in b["continuity"]["headline"]
    # direction HAS seeded route evidence -> a real recommendation grounded in it
    assert b["direction"]["task_classes"], "seeded route evidence should yield a recommendation"


def test_brief_is_read_only(demo_db):
    from helicon.brief import build_brief

    before = _conn(demo_db).execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    before_cubes = _conn(demo_db).execute("SELECT COUNT(*) FROM helicon_cubes").fetchone()[0]
    build_brief(_conn(demo_db))
    after = _conn(demo_db).execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    after_cubes = _conn(demo_db).execute("SELECT COUNT(*) FROM helicon_cubes").fetchone()[0]
    assert (before, before_cubes) == (after, after_cubes)
