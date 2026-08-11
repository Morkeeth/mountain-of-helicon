"""The complaint log's two authorship gates.

A correction is the only signal in this repo the machine cannot manufacture, so
the thing that must not break is WHOSE WORDS get stored. Everything else here is
a regex that can be widened later; the gates cannot be loosened without turning
the log into an agent grading its own output.
"""
import json

import pytest

from helicon import complaints
from helicon.db import init_db


def _entry(text, **over):
    e = {"type": "user", "message": {"content": text}, "promptSource": "typed",
         "sessionId": "s1", "cwd": "/Users/x/CODE/demo", "uuid": "u1",
         "timestamp": "2026-08-11T10:00:00Z"}
    e.update(over)
    return e


def _transcript(tmp_path, entries, name="p/sess.jsonl"):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries))
    return path


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


# --- gate 1: whose words are these -----------------------------------------

@pytest.mark.parametrize("over,kept", [
    ({}, True),                                    # typed
    ({"promptSource": "queued"}, True),            # typed while busy — still his
    ({"promptSource": "sdk"}, False),              # a programmatic judge run
    ({"promptSource": "system"}, False),           # task notification / peer agent
    ({"promptSource": None}, False),               # bash-input and friends
    ({"isMeta": True}, False),                     # injected skill body
    ({"toolUseResult": {"x": 1}}, False),          # a tool result, not a turn
])
def test_only_human_authored_turns_survive_gate_one(tmp_path, over, kept):
    path = _transcript(tmp_path, [_entry("no, that is wrong", **over)])
    assert bool(complaints.authored_turns(str(path))) is kept


def test_a_peer_agents_message_is_never_a_complaint(tmp_path, conn):
    """The exact shape that made this gate necessary: another Claude session's
    message arrives as a `type: user` entry and is full of imperatives. Counting
    it as human feedback would let agents write their own eval."""
    peer = _entry("no, stop — you did not do what I asked. Revert it.",
                  promptSource="system", isMeta=True)
    _transcript(tmp_path, [peer], name="p/peer.jsonl")

    result = complaints.scan(conn, projects_dir=str(tmp_path))

    assert result["complaints_found"] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE type='complaint'").fetchone()[0] == 0


# --- gate 2: is this his writing, or something he pasted --------------------

def test_a_short_correction_is_a_pushback():
    assert complaints.is_pushback("no, that is not what I asked for")


def test_a_long_pasted_brief_is_not_a_pushback():
    """`promptSource` says typed because he pressed enter, but the words are an
    agent-drafted lane prompt. Any correction-shaped phrase inside sits deep in
    the body, which is what separates it."""
    pasted = ("You are the overnight triage engineer. Orient: git log, README. "
              * 12) + " no, that is wrong"
    assert not complaints.is_pushback(pasted)


def test_a_correction_buried_deep_in_a_short_turn_is_not_a_pushback():
    assert not complaints.is_pushback("x" * (complaints.HEAD_CHARS + 20) + ". no, that is wrong")


def test_a_long_pushback_that_opens_with_the_correction_still_counts():
    """The first version capped length at 400 chars. Measured on the real corpus
    that cap rejected 3 turns and 2 were genuine — a long, detailed objection is
    still an objection, and losing it is worse than the one paste it caught."""
    long_real = ("no, mac OS we pilot it. in case it doesnt work or takes too much time "
                 "we pull back and dont demo it, but we should already highlight the "
                 "vision and the goal is to have it working. " * 3)
    assert len(long_real) > 400
    assert complaints.is_pushback(long_real)


def test_an_ordinary_instruction_is_not_a_pushback():
    assert not complaints.is_pushback("build the fleet board and push it")


# --- labelling --------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("no, we do the research tonight", "wrong-plan"),
    ("no i didnt post hi ledger, that was a year ago", "stale-or-false"),
    ("no clue what arize is", "wrong-model"),
    ("NO PLEASEE i dont want to verify stupid details", "over-scope"),
    ("no this is great, i love reviewing", "agreement"),
])
def test_labels_come_from_what_he_actually_says(text, expected):
    assert complaints.label(text) == expected


def test_agreement_is_labelled_not_hidden():
    """"no this is great" is a false positive of the detector. Filtering it out
    would flatter the yield; labelling it lets the error rate be counted."""
    assert complaints.label("no this is great, i love it") == "agreement"


# --- storage ----------------------------------------------------------------

def test_scan_stores_the_complaint_verbatim(tmp_path, conn):
    text = "no, i just want a table here"
    _transcript(tmp_path, [_entry(text)])

    complaints.scan(conn, projects_dir=str(tmp_path))

    row = conn.execute(
        "SELECT content, type, metadata FROM helicon_cubes WHERE type='complaint'").fetchone()
    assert row["content"] == text, "a summarised correction loses the thing worth keeping"
    meta = json.loads(row["metadata"])
    assert meta["label"] == "over-scope"
    assert meta["project"] == "demo"


def test_rescanning_stores_nothing_new(tmp_path, conn):
    """It has to be safe on a timer, or it will only run when someone remembers."""
    _transcript(tmp_path, [_entry("no, that is not what I asked for")])

    first = complaints.scan(conn, projects_dir=str(tmp_path))
    second = complaints.scan(conn, projects_dir=str(tmp_path))

    assert first["newly_stored"] == 1
    assert second["complaints_found"] == 1, "it still SEES it"
    assert second["newly_stored"] == 0, "it just does not store it twice"
    assert conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE type='complaint'").fetchone()[0] == 1


def test_no_new_table_was_added(conn):
    """The constraint was explicit: 38 tables was already too many."""
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "complaints" not in names
    assert "complaint_log" not in names
