"""Steps 5 and 6 of the real-work loop — the two the V2.3 audit found ABSENT.

Step 5: an accepted ruling improves the next run.
Step 6: the receipt distinguishes recorded / delivered / obeyed.

Both were "implemented" in the sense that rows were written. Neither was true in
the sense that anything read them. These tests assert the READ side, because the
write side already had passing tests and they proved nothing.
"""
import pytest

from helicon import capture, taskrun
from helicon.db import init_db


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "loop.db"))


def _accepted_run(conn, objective, prompt_text):
    rid = taskrun.open_run(conn, objective, "acceptance", harness="test",
                           repo_ref="/tmp/x@abc")
    taskrun.build_packet(conn, rid, query=objective[:20])
    taskrun.attach_artifact(conn, rid, [{"path": "f.py"}])
    taskrun.accept_run(conn, rid, "accepted", note="")
    conn.execute(
        "INSERT INTO run_captures (id, task_run_id, prompt_chain, captured_at, repo, "
        "provenance) VALUES (?,?,?,?,?,?)",
        ("rc_" + rid, rid, '[{"text": "%s"}]' % prompt_text, "2026-07-22", "/tmp/x",
         "governed"))
    conn.commit()
    capture.promote_prompt(conn, rid)
    return rid


# ---------------------------------------------------------------- step 5

def test_an_accepted_prompt_is_offered_on_the_next_similar_run(conn):
    """The edge the whole product rests on. Before this, prompt_library was
    written by capture.py and read by NOTHING — the promotion was inert."""
    _accepted_run(conn, "refactor the payment retry handler",
                  "Refactor the retry handler. Keep the idempotency key.")
    hits = capture.suggest_prompt(conn, "refactor the payment retry logic")
    assert hits, "an accepted prompt must reach the next comparable run"
    assert "idempotency" in hits[0]["prompt"]
    assert hits[0]["objective"] == "refactor the payment retry handler"


def test_an_unrelated_objective_gets_no_suggestion(conn):
    """A confident-looking wrong suggestion is worse than none."""
    _accepted_run(conn, "refactor the payment retry handler", "some prompt")
    assert capture.suggest_prompt(conn, "write a blog post about mountains") == []


def test_only_accepted_runs_ever_suggest(conn):
    """The outcome gate is the point: a reworked run's prompt must never be
    offered as though it had worked."""
    rid = taskrun.open_run(conn, "refactor the payment retry handler", "acc",
                           harness="test", repo_ref="/tmp/x@abc")
    taskrun.build_packet(conn, rid, query="refactor")
    taskrun.attach_artifact(conn, rid, [{"path": "f.py"}])
    taskrun.accept_run(conn, rid, "rework", note="")
    assert capture.promote_prompt(conn, rid)["ok"] is False
    assert capture.suggest_prompt(conn, "refactor the payment retry logic") == []


# ---------------------------------------------------------------- step 6

def test_receipt_states_all_three_delivery_states(conn):
    rid = _accepted_run(conn, "some objective", "p")
    receipt = taskrun.render_receipt(conn, rid)
    assert "recorded" in receipt
    assert "delivered" in receipt
    assert "obeyed" in receipt


def test_receipt_never_claims_obeyed(conn):
    """Delivered-is-not-obeyed is the honesty line. Only a run's output could
    show obedience and nothing here observes that."""
    rid = _accepted_run(conn, "some objective", "p")
    assert "obeyed: unproven" in taskrun.render_receipt(conn, rid)


def test_cockpit_reports_only_delivery_of_the_specific_correction(conn):
    """cockpit._delivery_state hardcoded delivered_to_live_run=False, so after
    the hook genuinely delivered a ruling the UI still said it had not."""
    from helicon.cockpit import _delivery_state
    conn.execute(
        "INSERT INTO helicon_cubes (id, source, source_ref, type, title, content, "
        "content_hash, created_at, valid_from, review_status) "
        "VALUES ('c1','output-review','r','note','t','c','h1','2026-07-01',"
        "'2026-07-01','approved')")
    conn.commit()

    assert _delivery_state(conn, "c1")["delivered_to_live_run"] is False

    conn.execute("INSERT INTO run_events (task_run_id, ts, kind, actor, detail) "
                 "VALUES ('hook:s1','2026-07-22','delivered','helicon',"
                 "'{\"cube_id\":\"unrelated\"}')")
    conn.commit()
    assert _delivery_state(conn, "c1")["delivered_to_live_run"] is False

    conn.execute("INSERT INTO run_events (task_run_id, ts, kind, actor, detail) "
                 "VALUES ('hook:s2','2026-07-22','delivered','helicon',"
                 "'{\"cube_id\":\"c1\"}')")
    conn.commit()
    state = _delivery_state(conn, "c1")
    assert state["delivered_to_live_run"] is True
    assert state["delivered_count"] == 1
    assert state["obeyed"] is None, "obeyed must stay unasserted"
