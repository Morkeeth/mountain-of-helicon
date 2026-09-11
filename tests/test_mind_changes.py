"""What changed my mind? Synthetic fixtures only; no personal memory is read."""
import json

import pytest

from helicon.mind_changes import answer, memory_passages, save_lesson

PERMIT = """---
name: notes-boundary
description: Whether agents may write to the shared review note.
metadata:
  modified: 2026-08-01T10:00:00Z
---

## Current ruling · 2026-09-09

Oscar: "you broke my human note, this is not OK, it is human written, I copy paste"

The shared review note is read-only for agents. Deliver proposed text in chat.

## History

**Lifted 2026-08-20.** Oscar, verbatim: *"you're allowed to write in the review note, permission done."*
"""

DECOY = """---
name: review-board-habit
description: How the review board is delivered.
metadata:
  modified: 2026-08-25T10:00:00Z
---

On 2026-08-25 Oscar said "the review note is faster than anything else by far".
Agents may create and update the review note board directly; creating and updating
review note boards is now authorized. Related: [[notes_boundary]].
"""

PRIVATE = """---
name: money-habits
description: private
metadata:
  modified: 2026-09-10T10:00:00Z
---

On 2026-09-10 Oscar said "do not open my wallet balance in the review note board".
"""

Q = "can agents create and update review note boards"


@pytest.fixture
def mem(tmp_path):
    d = tmp_path / "memory"
    d.mkdir()
    (d / "notes_boundary.md").write_text(PERMIT)
    (d / "review_board_habit.md").write_text(DECOY)
    return d


def test_content_date_beats_stale_frontmatter(mem):
    rows = {p["line"]: p for p in memory_passages(mem) if p["file"] == "notes_boundary.md"}
    dates = sorted((p["date"], p["date_source"]) for p in rows.values())
    assert ("2026-09-09", "heading") in dates
    assert ("2026-08-20", "text") in dates
    assert all(d != "2026-08-01" for d, _ in dates)


def test_attractive_old_decoy_loses_to_recent_correction(mem):
    res = answer(Q, window=30, as_of="2026-09-11", memory_dir=mem)
    item = res["items"][0]
    assert item["current"][0]["date"] == "2026-09-09"
    assert "read-only" in item["current"][0]["text"]
    decoy = [d for d in item["decoys"] if d["file"] == "review_board_habit.md"]
    assert decoy and decoy[0]["score"] > decoy[0]["current_score"]
    assert decoy[0]["superseded_by"] == "2026-09-09"
    assert item["changed_in_window"] is True


def test_later_correction_changes_the_recommendation(mem):
    before = answer(Q, window=30, as_of="2026-09-08", memory_dir=mem)["items"][0]
    after = answer(Q, window=30, as_of="2026-09-11", memory_dir=mem)["items"][0]
    assert before["current"][0]["date"] == "2026-08-25"
    assert "authorized" in before["lesson"]
    assert after["current"][0]["date"] == "2026-09-09"
    assert before["lesson"] != after["lesson"]
    assert "2026-09-09" in after["next_prompt"] and "Superseded" in after["next_prompt"]


def test_unavailable_evidence_is_a_gap_not_a_lesson(mem):
    res = answer("what did we set for the podcast pricing", window=7, as_of="2026-09-11",
                 memory_dir=mem)
    assert res["items"] == []
    assert res["gap"]["lesson"] is None
    # Evidence outside the window is also a gap, not a recycled old lesson.
    old = answer(Q, window=7, as_of="2026-09-30", memory_dir=mem)
    assert old["items"] == [] and old["gap"]


def test_personal_material_is_redacted_and_counted(mem):
    (mem / "money_habits.md").write_text(PRIVATE)
    res = answer("", window=7, as_of="2026-09-11", memory_dir=mem)
    blob = json.dumps(res)
    assert "wallet balance" not in blob
    assert sum(res["redactions"].values()) >= 1


def test_lesson_packet_refuses_personal_material(tmp_path):
    ok = save_lesson("Deliver note text in chat.", "prompt", [{"path": "x", "date": "2026-09-09"}],
                     tmp_path / "out")
    assert json.loads(open(ok["path"]).read())["lesson"] == "Deliver note text in chat."
    with pytest.raises(ValueError):
        save_lesson("Check the wallet seed phrase", "p", [], tmp_path / "out")
