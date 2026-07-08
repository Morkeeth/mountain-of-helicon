"""The consistency gate must catch real index/directory drift and, just as
importantly, must NOT cry wolf on links that legitimately point elsewhere."""
import os

from helicon.consistency import audit_index


def _write(p, text):
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def test_catches_dangling_and_unlisted(tmp_path):
    d = tmp_path
    _write(d / "alive.md", "here")
    _write(d / "orphan.md", "on disk but never named by the index")
    _write(d / "INDEX.md",
           "# Index\n- [alive](alive.md)\n- [gone](deleted.md)\n")
    res = audit_index(str(d / "INDEX.md"))
    assert res["ok"]
    assert "deleted.md" in res["dangling"]        # points at a ghost
    assert "orphan.md" in res["unlisted"]          # hides on disk
    assert "alive.md" not in res["unlisted"]
    assert not res["consistent"]


def test_clean_index_is_consistent(tmp_path):
    d = tmp_path
    _write(d / "a.md", "a")
    _write(d / "b.md", "b")
    _write(d / "INDEX.md", "# Index\n- [a](a.md)\n- [b](b.md)\n")
    res = audit_index(str(d / "INDEX.md"))
    assert res["consistent"]
    assert res["dangling"] == [] and res["unlisted"] == []


def test_grouped_subindex_counts_as_named(tmp_path):
    """A file named only by stem in a linked sub-index is not 'unlisted'."""
    d = tmp_path
    _write(d / "feedback_no_fake_data.md", "rule")
    _write(d / "feedback_index.md", "# Feedback\n- **no_fake_data** the rule\n")
    _write(d / "INDEX.md", "# Index\nsee [feedback_index.md](feedback_index.md)\n")
    res = audit_index(str(d / "INDEX.md"))
    assert "feedback_no_fake_data.md" not in res["unlisted"]


def test_external_links_not_flagged(tmp_path):
    """A link pointing outside the indexed directory is external, not dangling."""
    d = tmp_path
    sub = d / "mem"
    sub.mkdir()
    _write(sub / "INDEX.md", "# Index\n- [vault](../../elsewhere/thing.md)\n")
    res = audit_index(str(sub / "INDEX.md"))
    assert res["dangling"] == []
    assert len(res["external"]) == 1
