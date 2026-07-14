"""helicon runs, slice 1.1 - the cost side of run scoring.

Hermetic: synthetic .jsonl files in tmp_path, no real transcripts. The invariants:
usage sums come from the top-level fields (not the double-counting `iterations`),
duration is the timestamp span, and a file with no assistant/usage lines yields no
record (never a fabricated zero-cost run).
"""
import json

import pytest

from helicon.runs import parse_session_cost, scan_session_costs


def _write(path, lines):
    with open(path, "w") as fh:
        for o in lines:
            fh.write(json.dumps(o) + "\n")


def _assistant(ts, out, inp=0, cc=0, cr=0, model="claude-opus-4-8"):
    return {"type": "assistant", "timestamp": ts,
            "message": {"model": model, "usage": {
                "output_tokens": out, "input_tokens": inp,
                "cache_creation_input_tokens": cc, "cache_read_input_tokens": cr,
                # iterations repeats the same numbers; must NOT be summed again
                "iterations": [{"output_tokens": out, "input_tokens": inp}]}}}


def test_sums_usage_and_span(tmp_path):
    p = tmp_path / "sess-a.jsonl"
    _write(p, [
        {"type": "user", "timestamp": "2026-07-14T10:00:00.000Z"},
        _assistant("2026-07-14T10:05:00.000Z", out=100, inp=500, cc=200, cr=50),
        _assistant("2026-07-14T10:20:00.000Z", out=300, inp=700, cc=0, cr=1000),
    ])
    r = parse_session_cost(str(p))
    assert r["output_tokens"] == 400            # 100 + 300, NOT doubled by iterations
    assert r["input_tokens"] == 1200
    assert r["cache_creation_tokens"] == 200
    assert r["cache_read_tokens"] == 1050
    assert r["total_tokens"] == 400 + 1200 + 200 + 1050
    assert r["assistant_msgs"] == 2
    assert r["duration_min"] == 20.0            # 10:00 -> 10:20
    assert r["model"] == "claude-opus-4-8"


def test_dominant_model_wins(tmp_path):
    p = tmp_path / "sess-b.jsonl"
    _write(p, [
        _assistant("2026-07-14T10:00:00.000Z", out=10, model="claude-opus-4-8"),
        _assistant("2026-07-14T10:01:00.000Z", out=10, model="claude-opus-4-8"),
        _assistant("2026-07-14T10:02:00.000Z", out=10, model="claude-fable-5"),
    ])
    assert parse_session_cost(str(p))["model"] == "claude-opus-4-8"


def test_no_usage_file_is_no_record(tmp_path):
    p = tmp_path / "empty.jsonl"
    _write(p, [
        {"type": "user", "timestamp": "2026-07-14T10:00:00.000Z"},
        {"type": "system", "timestamp": "2026-07-14T10:01:00.000Z"},
    ])
    assert parse_session_cost(str(p)) is None   # never a fabricated zero-cost run


def test_scan_sorts_newest_first_and_since_filters(tmp_path):
    _write(tmp_path / "old.jsonl", [_assistant("2026-07-01T10:00:00.000Z", out=10)])
    _write(tmp_path / "new.jsonl", [_assistant("2026-07-14T10:00:00.000Z", out=10)])
    recs = scan_session_costs(str(tmp_path))
    assert [r["session_id"] for r in recs] == ["new", "old"]     # newest first
    recent = scan_session_costs(str(tmp_path), since="2026-07-10")
    assert [r["session_id"] for r in recent] == ["new"]         # since drops old
