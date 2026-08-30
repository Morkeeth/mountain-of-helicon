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


# --- the gate must read the whole directory, and must not cry wolf on an archive ---
#
# Written against the requirement, not against the implementation: a gate whose
# job is "does the index match the directory" is not allowed to answer over a
# subset it silently chose. Measured on the real memory directory 2026-08-27, the
# one-level version read 273 of 352 and still printed a verdict.


def test_reads_nested_files_not_only_the_top_level(tmp_path):
    """A file one directory down is part of the corpus, not invisible."""
    d = tmp_path
    (d / "notes").mkdir()
    _write(d / "listed.md", "listed")
    _write(d / "notes" / "buried.md", "on disk, one level down, never named")
    _write(d / "INDEX.md", "# Index\n- [listed](listed.md)\n")
    res = audit_index(str(d / "INDEX.md"))
    assert res["scanned"] == 2, "the index file itself is excluded; both others count"
    assert os.path.join("notes", "buried.md") in res["unlisted"]
    assert not res["consistent"]


def test_scanned_is_the_denominator_and_survives_depth(tmp_path):
    """Depth must not change the population, only where files sit in it."""
    d = tmp_path
    deep = d / "a" / "b" / "c"
    deep.mkdir(parents=True)
    _write(d / "top.md", "t")
    _write(d / "a" / "one.md", "1")
    _write(deep / "four.md", "4")
    _write(d / "INDEX.md", "# Index\n- [top](top.md)\n")
    res = audit_index(str(d / "INDEX.md"))
    assert res["scanned"] == 3


def test_archived_files_are_counted_not_flagged(tmp_path):
    """An archive is the convention working. Scanning it is required; flagging
    it is the drift-fatigue that gets a gate switched off."""
    d = tmp_path
    (d / "archive").mkdir()
    _write(d / "live.md", "live")
    _write(d / "archive" / "old-receipt.md", "correctly archived, not named anywhere")
    _write(d / "INDEX.md", "# Index\n- [live](live.md)\n\nOlder -> archive/\n")
    res = audit_index(str(d / "INDEX.md"))
    assert res["scanned"] == 2, "the archived file is READ"
    assert res["archived"] == 1
    assert res["on_disk"] == 1, "live count excludes the archive"
    assert res["unlisted"] == [], "an archived file is never unlisted"
    assert os.path.join("archive", "old-receipt.md") in res["archived_unlisted"]
    assert res["consistent"], "a correctly-archived file does not fail the gate"


def test_an_archive_does_not_hide_live_drift(tmp_path):
    """The negative control for the rule above: the archive exemption must not
    become a way for real drift to pass. Strip the archive and the finding stands."""
    d = tmp_path
    (d / "archive").mkdir()
    _write(d / "archive" / "old.md", "archived")
    _write(d / "orphan.md", "live, on disk, never named")
    _write(d / "INDEX.md", "# Index\n(nothing)\n")
    res = audit_index(str(d / "INDEX.md"))
    assert "orphan.md" in res["unlisted"]
    assert not res["consistent"]


def test_wikilink_into_the_archive_is_not_dangling(tmp_path):
    """The one-level read reported a moved file as a ghost. It is right there."""
    d = tmp_path
    (d / "archive").mkdir()
    _write(d / "archive" / "moved-note.md", "still exists, just archived")
    _write(d / "INDEX.md", "# Index\nsee [[moved-note]]\n")
    res = audit_index(str(d / "INDEX.md"))
    assert res["dangling_wikilinks"] == []
