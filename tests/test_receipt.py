"""The receipt — proving an injection was RECEIVED, not asserting it.

`hook_deliver` writes a 'delivered' row and returns. That row is Helicon
vouching for Helicon: it proves this process decided to inject, not that the
harness got anything. The receipt closes that by reading the transcript the
HARNESS wrote and looking for a content-derived token.

Pins:
- the token is in the transcript      -> RECEIVED, with the line number
- the transcript exists and lacks it  -> NOT_FOUND (a real miss, said plainly)
- no transcript / no injection        -> UNVERIFIABLE, never rounded up
- the token is derived from the bytes, so a different injection cannot satisfy it
- an injection that would blow the context-rot budget is TRIMMED and the trim is
  recorded, because a memory tool causing context rot is the joke writing itself
"""
import json

import pytest

from helicon import capture
from helicon.db import init_db, insert_cube
from helicon.models import HeliconCube
from helicon.scanner import make_id, content_hash


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


def _seed_ruling(conn, text, created="2026-07-22T00:00:00"):
    c = HeliconCube(
        id=make_id(), source="output-review", source_ref="audit:1", type="decision",
        title="Output-checked", content=text, summary="",
        content_hash=content_hash(text), created_at=created,
        valid_from=created, last_reinforced=created,
        confidence=1.0, review_status="approved")
    insert_cube(conn, c)
    conn.commit()
    return c.id


def _transcript(tmp_path, *lines):
    p = tmp_path / "transcript.jsonl"
    p.write_text("\n".join(json.dumps({"type": "user", "content": l}) for l in lines))
    return str(p)


# --------------------------------------------------------------------------

def test_received_when_the_token_is_in_the_harness_transcript(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "_safe_repo_root", lambda p, ar=None: "/safe")
    _seed_ruling(conn, "the suite is 619 not 580")

    tpath = str(tmp_path / "t.jsonl")
    ctx = capture.hook_deliver(conn, "/safe/repo", session="sess1",
                               transcript_path=tpath)
    assert ctx and capture.RECEIPT_MARK in ctx

    # the harness writes the injected text into its own transcript
    token = capture.receipt_token(ctx.rsplit("\n\n" + capture.RECEIPT_MARK, 1)[0])
    with open(tpath, "w") as fh:
        fh.write(json.dumps({"type": "user", "content": "hello"}) + "\n")
        fh.write(json.dumps({"type": "user", "content": ctx}) + "\n")

    r = capture.receipt(conn, "sess1")
    assert r["verdict"] == "RECEIVED"
    assert r["line"] == 2
    assert r["token"] == token
    assert "619 not 580" not in r["why"]          # the verdict is about receipt


def test_not_found_when_the_transcript_lacks_the_token(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "_safe_repo_root", lambda p, ar=None: "/safe")
    _seed_ruling(conn, "a ruling")
    tpath = _transcript(tmp_path, "some unrelated turn")
    capture.hook_deliver(conn, "/safe/repo", session="sessA", transcript_path=tpath)

    r = capture.receipt(conn, "sessA")
    assert r["verdict"] == "NOT_FOUND"
    assert "did not reach" in r["why"]


def test_unverifiable_when_the_harness_gave_no_transcript(conn, monkeypatch):
    """A delivery we cannot check is a delivery we have not proven. This is the
    verdict the whole repo's honesty rule exists for — it must never quietly
    become RECEIVED."""
    monkeypatch.setattr(capture, "_safe_repo_root", lambda p, ar=None: "/safe")
    _seed_ruling(conn, "a ruling")
    capture.hook_deliver(conn, "/safe/repo", session="sessB", transcript_path="")

    r = capture.receipt(conn, "sessB")
    assert r["verdict"] == "UNVERIFIABLE"
    assert "no transcript_path" in r["why"]


def test_unverifiable_when_the_transcript_is_gone(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "_safe_repo_root", lambda p, ar=None: "/safe")
    _seed_ruling(conn, "a ruling")
    capture.hook_deliver(conn, "/safe/repo", session="sessC",
                         transcript_path=str(tmp_path / "vanished.jsonl"))
    r = capture.receipt(conn, "sessC")
    assert r["verdict"] == "UNVERIFIABLE"
    assert "not found" in r["why"]


def test_unverifiable_when_nothing_was_ever_injected(conn):
    r = capture.receipt(conn, "never-happened")
    assert r["verdict"] == "UNVERIFIABLE"
    assert "no injection logged" in r["why"]


def test_a_different_injection_cannot_satisfy_the_receipt(conn, tmp_path, monkeypatch):
    """The token is derived from the injected bytes, so a transcript containing
    some OTHER Helicon injection does not count as having received this one."""
    monkeypatch.setattr(capture, "_safe_repo_root", lambda p, ar=None: "/safe")
    _seed_ruling(conn, "ruling one")
    ctx1 = capture.hook_deliver(conn, "/safe/repo", session="s1",
                                transcript_path=str(tmp_path / "a.jsonl"))

    _seed_ruling(conn, "ruling two — different bytes", created="2026-07-23T00:00:00")
    tpath = str(tmp_path / "b.jsonl")
    ctx2 = capture.hook_deliver(conn, "/safe/repo", session="s2",
                                transcript_path=tpath)
    assert ctx1 != ctx2

    # the transcript for s2 contains the OLD injection only
    with open(tpath, "w") as fh:
        fh.write(json.dumps({"type": "user", "content": ctx1}) + "\n")

    assert capture.receipt(conn, "s2")["verdict"] == "NOT_FOUND"


# --------------------------------------------------------------------------
# the budget: Helicon must not cause the rot it detects
# --------------------------------------------------------------------------

def test_injection_is_trimmed_to_stay_under_the_context_rot_onset(conn, monkeypatch):
    monkeypatch.setattr(capture, "_safe_repo_root", lambda p, ar=None: "/safe")
    from helicon.context_budget import ONSET_TOKENS

    # 20 rulings of ~4k tokens each: far past the ~32k onset if all were sent
    for i in range(20):
        _seed_ruling(conn, f"ruling {i} " + ("x" * 16_000),
                     created=f"2026-07-{i + 1:02d}T00:00:00")

    ctx = capture.hook_deliver(conn, "/safe/repo", session="big",
                               transcript_path="/tmp/x.jsonl")
    assert ctx
    assert len(ctx) // 4 <= ONSET_TOKENS

    detail = json.loads(conn.execute(
        "SELECT detail FROM run_events WHERE kind='injected'").fetchone()["detail"])
    # the trim is RECORDED, not silent
    assert detail["rulings_trimmed"]
    assert detail["rulings_kept"] < 20
    assert detail["budget_status"] in ("healthy", "watch")


def test_a_small_injection_is_not_trimmed(conn, monkeypatch):
    monkeypatch.setattr(capture, "_safe_repo_root", lambda p, ar=None: "/safe")
    _seed_ruling(conn, "short ruling")
    capture.hook_deliver(conn, "/safe/repo", session="small", transcript_path="")
    detail = json.loads(conn.execute(
        "SELECT detail FROM run_events WHERE kind='injected'").fetchone()["detail"])
    assert detail["rulings_trimmed"] == []
    assert detail["rulings_kept"] == 1
    assert detail["budget_status"] == "healthy"


def test_format_receipt_states_the_verdict_first(conn):
    out = capture.format_receipt(capture.receipt(conn, "nope"))
    assert "UNVERIFIABLE" in out.splitlines()[1]
