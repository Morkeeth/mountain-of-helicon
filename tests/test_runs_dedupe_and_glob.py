"""Two defects in the cost parser, both measured against real transcripts first.

`tests/test_runs.py` already guards one double-count: the `iterations` sub-list
inside a single `usage` object. It never guarded the bigger one, which is one
level up.

DEFECT 1, THE CONTENT-BLOCK REPEAT. Claude Code writes one transcript LINE per
content block of the same API message. A turn with a text block and a tool_use
block is two lines carrying the identical `usage` object and the identical
`message.id`. Summing lines counts that turn twice.

  Measured on a real transcript, ~/.claude/projects/-Users-morkeeth/
  fe3d27c4-449a-4159-aec9-14e208fac179.jsonl, on 2026-09-16:
  250 assistant lines carry usage, they hold 112 distinct `message.id` values,
  and 76 of those ids repeat, with counts of 2 and 3.

  Measured across the 270 files in that directory on the same day:
  summing lines gives 33,565,336,803 tokens, deduping on `message.id` gives
  16,375,477,986. The parser is 2.05x high.

Transcripto has deduped on this key since it was written (`transcripto.py:679`).
Helicon did not, so the same machine reports two different numbers for the same
files depending on which tool is asked.

DEFECT 2, THE FLAT GLOB. `scan_session_costs` globbed `*.jsonl` in the project
directory only. Subagent and workflow transcripts live in subdirectories.

  Measured in the same directory on 2026-09-16: the flat glob finds 270 files,
  a recursive glob finds 2,070. The parser was blind to 87 percent of the
  transcripts, and every one it missed was subagent work, which is real spend.

Both tests below fail against the shipped parser. The numbers in them are the
fixture's own, chosen so that the naive result and the correct result cannot be
confused for each other.
"""
import json

from helicon.runs import parse_session_cost, scan_session_costs


def _write(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        for o in lines:
            fh.write(json.dumps(o) + "\n")


def _block(msg_id, ts, out, cr, model="claude-opus-5"):
    """One transcript LINE. Several lines can share one msg_id, exactly as
    Claude Code writes them, and then they carry the same usage object."""
    return {"type": "assistant", "timestamp": ts,
            "message": {"id": msg_id, "model": model,
                        "usage": {"output_tokens": out, "input_tokens": 0,
                                  "cache_creation_input_tokens": 0,
                                  "cache_read_input_tokens": cr}}}


# One API message written across two lines (text block + tool_use block),
# then a second API message written across one line.
#   naive, per line:  (100 + 1000) * 2  +  (50 + 2000)  = 4250
#   correct, per id:  (100 + 1000)      +  (50 + 2000)  = 3150
TWO_BLOCK_TURN = [
    _block("msg_a", "2026-09-16T10:00:00.000Z", out=100, cr=1000),
    _block("msg_a", "2026-09-16T10:00:00.000Z", out=100, cr=1000),
    _block("msg_b", "2026-09-16T10:05:00.000Z", out=50, cr=2000),
]
NAIVE_TOTAL = 4250
CORRECT_TOTAL = 3150


def test_repeated_message_id_is_counted_once(tmp_path):
    """The defect, stated as the two numbers it sits between.

    Against the shipped parser this returns NAIVE_TOTAL and the test goes red.
    """
    p = tmp_path / "sess-dupe.jsonl"
    _write(p, TWO_BLOCK_TURN)
    r = parse_session_cost(str(p))

    assert r["total_tokens"] != NAIVE_TOTAL, \
        "summing transcript lines counts a multi-block turn twice"
    assert r["total_tokens"] == CORRECT_TOTAL
    assert r["output_tokens"] == 150
    assert r["cache_read_tokens"] == 3000


def test_assistant_msgs_counts_api_messages_not_lines(tmp_path):
    """`assistant_msgs` is a denominator elsewhere, so an inflated count is not
    a cosmetic error. Two API messages were sent, across three lines."""
    p = tmp_path / "sess-count.jsonl"
    _write(p, TWO_BLOCK_TURN)
    assert parse_session_cost(str(p))["assistant_msgs"] == 2


def test_a_line_without_a_message_id_still_counts(tmp_path):
    """Dedupe must not become a silent drop. A line with no `message.id` has no
    key to dedupe on, so it counts, once. Losing spend is as wrong as doubling
    it, and it fails in the direction nobody audits."""
    p = tmp_path / "sess-nokey.jsonl"
    _write(p, [
        {"type": "assistant", "timestamp": "2026-09-16T10:00:00.000Z",
         "message": {"model": "claude-opus-5",
                     "usage": {"output_tokens": 7, "input_tokens": 0,
                               "cache_creation_input_tokens": 0,
                               "cache_read_input_tokens": 0}}},
        _block("msg_z", "2026-09-16T10:01:00.000Z", out=3, cr=0),
    ])
    r = parse_session_cost(str(p))
    assert r["output_tokens"] == 10
    assert r["assistant_msgs"] == 2


def test_dedupe_is_scoped_to_one_file(tmp_path):
    """Two different sessions can hold the same id only by accident, but a
    dedupe set shared across files would silently delete a whole session's
    spend. Each file is parsed on its own.

    THE DATA CONTRADICTED THIS TEST'S PREMISE. Do not read it as an intended
    contract. It describes what `runs.py` does today, and that behaviour is
    scheduled to be inverted.

    The premise was that a repeated id across files is an accidental collision.
    It is not. Measured over a frozen copy of 2,084 real transcripts on
    2026-09-16: exactly 2 message ids appear in more than one file, 3 extra
    occurrences in total, and every one of them is a parent transcript sharing
    a message with its OWN subagent transcript, for example
    `0efbd36a-....jsonl` and `0efbd36a-.../subagents/agent-a30587bf....jsonl`.
    The API billed that message once. Counting it twice is the defect, and
    per-file scoping is what causes it. Transcripto dedupes globally across the
    whole scan and is right to.

    The cost of the bug it does guard against is 741,367 tokens on that corpus,
    or 0.004 percent. The cost of the bug it causes is the same number, with
    the opposite sign.

    When the shared core lands (spec section 12), this test is inverted to
    assert global dedupe, or deleted. It stays for now because a test that
    lies about current behaviour is worse than one that describes a behaviour
    due to change.

    One thing stays unverified either way: the same id carries slightly
    different usage numbers in different files, 316,085 against 312,535 in the
    example above. Which copy is authoritative is not settled, so "keep the
    first" is a choice, not a finding.
    """
    _write(tmp_path / "one.jsonl",
           [_block("msg_shared", "2026-09-16T10:00:00.000Z", out=11, cr=0)])
    _write(tmp_path / "two.jsonl",
           [_block("msg_shared", "2026-09-16T11:00:00.000Z", out=11, cr=0)])
    recs = scan_session_costs(str(tmp_path))
    assert sorted(r["output_tokens"] for r in recs) == [11, 11]


def test_scan_finds_transcripts_in_subdirectories(tmp_path):
    """The flat glob missed 87 percent of the real corpus, all of it subagent
    work. A recursive glob finds them."""
    _write(tmp_path / "top.jsonl",
           [_block("m1", "2026-09-16T10:00:00.000Z", out=10, cr=0)])
    _write(tmp_path / "subagents" / "sub.jsonl",
           [_block("m2", "2026-09-16T10:01:00.000Z", out=20, cr=0)])
    _write(tmp_path / "subagents" / "workflows" / "wf_1" / "deep.jsonl",
           [_block("m3", "2026-09-16T10:02:00.000Z", out=30, cr=0)])

    recs = scan_session_costs(str(tmp_path))
    assert sorted(r["session_id"] for r in recs) == ["deep", "sub", "top"]
    assert sum(r["output_tokens"] for r in recs) == 60


def test_scan_still_sorts_and_filters_with_the_wider_glob(tmp_path):
    """Widening the population must not break the ordering and the `since`
    filter that `test_runs.py` already relies on."""
    _write(tmp_path / "old.jsonl",
           [_block("m1", "2026-07-01T10:00:00.000Z", out=10, cr=0)])
    _write(tmp_path / "nested" / "new.jsonl",
           [_block("m2", "2026-09-16T10:00:00.000Z", out=10, cr=0)])

    assert [r["session_id"] for r in scan_session_costs(str(tmp_path))] == ["new", "old"]
    assert [r["session_id"] for r in
            scan_session_costs(str(tmp_path), since="2026-08-01")] == ["new"]
