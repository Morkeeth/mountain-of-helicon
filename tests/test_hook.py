"""UserPromptSubmit hook — deliver approved rulings INTO a live session
(privacy-gated) and record provable delivery. Closes the delivery gap: a real
harness receives the rulings; not asserted from a DB write."""
import pytest

from helicon.db import init_db, insert_cube
from helicon.models import HeliconCube
from helicon.scanner import make_id, content_hash
from helicon import capture


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


def _seed_correction(conn, text):
    c = HeliconCube(
        id=make_id(), source="output-review", source_ref="audit:1", type="decision",
        title="Output-checked: helicon", content=text, summary="",
        content_hash=content_hash(text), created_at="2026-07-22T00:00:00",
        valid_from="2026-07-22T00:00:00", last_reinforced="2026-07-22T00:00:00",
        confidence=1.0, review_status="approved")
    insert_cube(conn, c)
    conn.commit()


def test_hook_delivers_rulings_and_records_provable_delivery(conn, monkeypatch):
    _seed_correction(conn, "the suite is 393 not 344; the closeout count is stale")
    monkeypatch.setattr(capture, "_safe_repo_root", lambda p, ar=None: "/safe")
    ctx = capture.hook_deliver(conn, "/safe/repo", session="sess1")
    assert ctx and "rulings to obey" in ctx
    assert "393 not 344" in ctx                       # the actual ruling is delivered
    # delivery is RECORDED (provable), not asserted
    n = conn.execute("SELECT COUNT(*) FROM run_events WHERE kind='delivered'").fetchone()[0]
    assert n == 1


def test_hook_blocks_a_private_repo(conn, monkeypatch):
    _seed_correction(conn, "secret ruling")
    monkeypatch.setattr(capture, "_safe_repo_root", lambda p, ar=None: None)  # private/unsafe
    assert capture.hook_deliver(conn, "/Users/x/CODE/rekt-capital", session="s") is None
    assert conn.execute("SELECT COUNT(*) FROM run_events").fetchone()[0] == 0  # nothing recorded


def test_hook_with_no_corrections_delivers_nothing(conn, monkeypatch):
    monkeypatch.setattr(capture, "_safe_repo_root", lambda p, ar=None: "/safe")
    assert capture.hook_deliver(conn, "/safe/repo") is None
