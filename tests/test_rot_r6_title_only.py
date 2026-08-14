"""R6 title-only grounding, from the sweep that caught it inverted.

Written from the 13-fixture sweep of 2026-08-14, before touching the class.
On a stranger's first run R6 was wrong in both directions at once:

  planted rot, reported CLEAN
    a CLAUDE.md of four headings and no content stored zero memories, and the
    share fell through an empty denominator to 0. Emptiness read as health.

  no rot, reported ROT FOUND
    "Format with black, line length 100." is 35 characters, so it was a stub.
    Three of the four CI FAILs in the sweep were this, on ordinary rules.

The rule these tests defend: a stub is a memory with no body, never a memory
with a short one, and no-memories is never CLEAN.
"""
import hashlib
import itertools

import pytest

from helicon.db import init_db
from helicon.rot import run_rot_exam

_seq = itertools.count()


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


def _add(conn, title, content):
    n = next(_seq)
    conn.execute(
        "INSERT INTO helicon_cubes (source, source_ref, type, title, content, "
        "content_hash, created_at, valid_from, review_status) "
        "VALUES ('agent-rules', ?, 'rule', ?, ?, ?, "
        "'2026-08-14T00:00:00', '2026-08-14T00:00:00', 'pending')",
        (f"CLAUDE.md#{n}", title, content,
         hashlib.sha256(f"{n}{content}".encode()).hexdigest()))
    conn.commit()


def _r6(conn):
    return next(c for c in run_rot_exam(conn)["checks"] if c["id"] == "R6")


# --- the shape test, independent of the exam ---------------------------------

@pytest.mark.parametrize("content", [
    "Format with black, line length 100.",           # 35 chars, whole rule
    "Run tests.",                                     # 10 chars, whole rule
    "Rotate the signing key quarterly.",              # flagged in the sweep
])
def test_short_and_complete_is_not_a_stub(content):
    # Imported inside the test, not at module scope. At module scope a build
    # without the helper produces a collection error, and a collection error is
    # not a watched failure — the same mistake this morning, in the same file.
    from helicon.rot import _title_only
    assert _title_only("[r] CLAUDE.md — Rules", content) is False


@pytest.mark.parametrize("content", [
    "",
    "   ",
    "## Testing\n## Deployment\n## Security",           # headings, no instruction
    "Rules",                                            # repeats the heading
])
def test_a_heading_with_nothing_under_it_is_a_stub(content):
    from helicon.rot import _title_only
    assert _title_only("[r] CLAUDE.md — Rules", content) is True


# --- the verdict tests -------------------------------------------------------

def test_no_memories_is_unmeasured_not_clean(conn):
    """The defect that let four empty headings score CLEAN."""
    r6 = _r6(conn)
    assert r6["verdict"] == "UNMEASURED"
    assert "unmeasured, not clean" in r6["receipt"]


def test_ordinary_short_rules_do_not_fire(conn):
    """The r10 fixture, verbatim: both rules real, both under 40 characters."""
    _add(conn, "[r10] CLAUDE.md — Rules", "Format with black, line length 100.")
    _add(conn, "[r10] .cursorrules — (rules)", "Format with ruff, line length 79.")
    r6 = _r6(conn)
    assert r6["verdict"] == "CLEAN"
    assert "0/2" in r6["receipt"]


def test_real_title_only_memories_still_fire(conn):
    """The fix must not buy a quiet R6 by making it unable to fire."""
    for n in range(3):
        _add(conn, f"[r] CLAUDE.md — Section {n}", "")
    _add(conn, "[r] CLAUDE.md — Real", "Never commit secrets; rotate keys quarterly.")
    r6 = _r6(conn)
    assert r6["verdict"] == "ROT FOUND"
    assert "3/4" in r6["receipt"]


def test_the_threshold_is_stated_in_the_receipt(conn):
    """A share with a hidden cutoff is a number the reader cannot check."""
    _add(conn, "[r] CLAUDE.md — Rules", "Format with black, line length 100.")
    assert "10%" in _r6(conn)["receipt"]
