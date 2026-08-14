"""Five classes called an absent history clean.

From the 13-fixture sweep of 2026-08-14. On a stranger's first run the exam
reported nine CLEAN, and five of those were arithmetic rather than evidence:

  R1  no dated fact and no scalar claim existed, so nothing was comparable
  R3  no memory was old enough for a half-life to have passed
  R5  a duplicate needs two memories and there were fewer than two
  R7  nothing had ever been retired, so nothing could be retired wrongly
  R9  no reviews existed, so the human-evidence guard was never asked
  R10 nothing had been retired as drifted, and drift needs a previous scan
  R12 no entities existed, so no relation could sit between two of them

R11 was found the same way one step later, and it hid best of the six: it fires
correctly when entities exist, so its own sweep fixture passed. On openai/codex
the scan extracted zero entities and R11 still printed CLEAN, two lines above
R12 printing "0 entity(s) extracted" in the same output.

R4 and R8 met the same emptiness and said UNMEASURED. The exam gave two
different answers to one situation and only one of them was true.

The rule these tests defend: any metric over a set needs an explicit answer for
the empty set, and that answer is never the healthy end of the scale.
"""
import hashlib
import itertools
import sqlite3

import pytest

from helicon.db import init_db
from helicon.rot import run_rot_exam

EMPTY_POPULATION = ["R1", "R3", "R5", "R7", "R9", "R10", "R11", "R12"]

_seq = itertools.count()


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


def _add(conn, title, content, status="pending", created="2026-08-14T00:00:00",
         mtype="rule"):
    n = next(_seq)
    conn.execute(
        "INSERT INTO helicon_cubes (source, source_ref, type, title, content, "
        "content_hash, created_at, valid_from, review_status) "
        "VALUES ('agent-rules', ?, ?, ?, ?, ?, ?, ?, ?)",
        (f"CLAUDE.md#{n}", mtype, title, content,
         hashlib.sha256(f"{n}{content}".encode()).hexdigest(),
         created, created, status))
    conn.commit()


def _verdicts(conn):
    return {c["id"]: c for c in run_rot_exam(conn)["checks"]}


@pytest.mark.parametrize("rid", EMPTY_POPULATION)
def test_an_empty_population_is_never_clean(conn, rid):
    """The whole finding, one class at a time, on a store with nothing in it."""
    check = _verdicts(conn)[rid]
    assert check["verdict"] == "UNMEASURED", check
    assert check["receipt"].startswith("nothing to grade:"), check


@pytest.mark.parametrize("rid", EMPTY_POPULATION)
def test_the_receipt_names_what_was_missing(conn, rid):
    """"nothing to grade" without the reason is the same silence in nicer
    words. A reader has to be able to tell WHY the class could not run."""
    receipt = _verdicts(conn)[rid]["receipt"]
    assert len(receipt) > len("nothing to grade: ") + 20, receipt


def test_a_first_run_on_ordinary_rules_still_cannot_claim_these(conn):
    """Two real, fresh, non-duplicate rules — the shape of an actual first run.
    Memories now exist, but no history does, so the five must still abstain."""
    _add(conn, "[r] CLAUDE.md — Rules", "Format with black, line length 100.")
    _add(conn, "[r] AGENTS.md — Rules", "Run the full suite before pushing.")
    checks = _verdicts(conn)
    for rid in ("R1", "R3", "R5", "R7", "R9", "R10", "R11", "R12"):
        assert checks[rid]["verdict"] == "UNMEASURED", checks[rid]


def test_r5_cannot_fire_at_all_and_says_so(conn):
    """Written as "R5 must still be able to fire", which is how the real defect
    surfaced: the insert raised UNIQUE constraint failed. helicon_cubes declares
    UNIQUE(content_hash), so R5's HAVING COUNT(*) > 1 can never match on any
    repo. It had been reporting CLEAN for a check the schema makes unfailable."""
    same = "Never commit secrets to the repository."
    digest = hashlib.sha256(same.encode()).hexdigest()

    def _insert(ref, title):
        conn.execute(
            "INSERT INTO helicon_cubes (source, source_ref, type, title, content, "
            "content_hash, created_at, valid_from, review_status) "
            "VALUES ('agent-rules', ?, 'rule', ?, ?, ?, "
            "'2026-08-14T00:00:00', '2026-08-14T00:00:00', 'pending')",
            (ref, title, same, digest))
        conn.commit()

    _insert("CLAUDE.md#1", "[r] one")
    with pytest.raises(sqlite3.IntegrityError):
        _insert("AGENTS.md#1", "[r] two")     # the constraint, watched firing
    r5 = _verdicts(conn)["R5"]
    assert r5["verdict"] == "UNMEASURED", r5
    assert "UNIQUE(content_hash)" in r5["receipt"], r5


def test_r3_fires_on_a_memory_old_enough_to_have_expired(conn):
    """The other half of the guard: R3 must still be able to say ROT FOUND."""
    _add(conn, "[r] CLAUDE.md — Old", "Use the beta billing API until March 2024.",
         created="2020-01-01T00:00:00", mtype="memory")
    _add(conn, "[r] CLAUDE.md — Old2", "Pin torch to 1.13 for the migration.",
         created="2020-01-01T00:00:00", mtype="decision")
    r3 = _verdicts(conn)["R3"]
    assert r3["verdict"] == "ROT FOUND", r3
