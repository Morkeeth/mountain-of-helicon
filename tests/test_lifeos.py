"""lifeos connector: the operator's second brain as section-level cubes.

Read-only markdown roots, frontmatter date over mtime (a banner stamp must
not rejuvenate a June doc), and strip_pattern so the rot benchmark can
remove the human answer key before ingest.
"""
import os

import pytest

from helicon.connectors import lifeos


@pytest.fixture
def roots(tmp_path):
    vault = tmp_path / "01 Projects"
    (vault / "Relay").mkdir(parents=True)
    (vault / "Relay" / "audit.md").write_text(
        "---\ndate: 2026-06-20\nstatus: point-in-time\n---\n"
        "> **LOUPE STATUS FLIP Jul 5: all fixes MERGED.**\n\n"
        "# Open items\nescrow gate NOT patched\n\n# Notes\npending merge\n")
    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "status.md").write_text("# Status\nall merged to main\n")
    return str(vault), str(memory)


def test_no_roots_is_silent_optin():
    assert lifeos.scan({}) == []


def test_section_cubes_with_frontmatter_date(roots):
    vault, memory = roots
    got = lifeos.scan({"roots": [vault, memory]})
    refs = {r.source_ref for r in got}
    assert "01 Projects/Relay/audit.md#open-items" in refs
    assert "memory/status.md#status" in refs
    audit = next(r for r in got if r.source_ref.endswith("#open-items"))
    assert audit.created_at == "2026-06-20T00:00:00"  # frontmatter, not mtime
    assert audit.source == "lifeos"
    assert audit.metadata["status"] == "point-in-time"


def test_strip_pattern_removes_the_answer_key(roots):
    vault, _ = roots
    got = lifeos.scan({"roots": [vault],
                       "strip_pattern": r"^> \*\*LOUPE"})
    assert all("LOUPE" not in r.content for r in got)
    # and without it, watch mode sees the banner
    got_all = lifeos.scan({"roots": [vault]})
    assert any("LOUPE" in r.content for r in got_all)


def test_spaces_in_paths_and_missing_roots(tmp_path, roots):
    vault, _ = roots
    got = lifeos.scan({"roots": [vault, str(tmp_path / "does not exist")]})
    assert got and all(r.source_ref.startswith("01 Projects/") for r in got)
