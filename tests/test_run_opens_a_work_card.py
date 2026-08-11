"""The Workgraph front door: a governed run leaves a Work Card behind.

`open_wager` is the only way a Work Card can exist, and before this it had no
caller outside tests/. `helicon_capture_launch` asks for a `wager_id` that no
CLI command and no MCP tool could produce, so the graph was enterable only at
step two — two live cards in two weeks, both hand-made. These tests pin the
door open: `run open` writes the card, `run close` writes its receipt, and
neither of them invents a claim the operator did not make.

Deliberately NOT asserted: that the card resolves. A closed run means the
artifact was accepted; a resolved card means the change was seen in the world.
test_close_does_not_resolve_the_card pins that they stay separate.
"""
import pytest

from helicon.cli import _close_work_card, _open_work_card
from helicon.db import init_db
from helicon.taskrun import accept_run, attach_artifact, build_packet, open_run
from helicon.wager import workgraph_attention


class Args:
    """The subset of the `helicon run` namespace the two helpers read."""

    def __init__(self, objective, acceptance, kill=None):
        self.objective = objective
        self.acceptance = acceptance
        self.kill = kill


CONTRACT = {
    "beneficiary": "Oscar",
    "observable_change": "work_wagers gains a row per governed run",
    "evidence_source": "sqlite: SELECT * FROM work_wagers",
}


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


def _run(conn, objective="ship the door", acceptance="a row exists"):
    rid = open_run(conn, objective, acceptance, harness="test")
    # The real `run open` freezes a packet before any artifact can attach; an
    # artifact on an un-packeted run is refused by taskrun, so mirror the order.
    build_packet(conn, rid, query=objective)
    return rid


def test_open_writes_a_linked_card(conn):
    rid = _run(conn)
    card_id = _open_work_card(conn, rid, Args("ship the door", "a row exists"), CONTRACT)

    assert card_id
    row = conn.execute("SELECT * FROM work_wagers WHERE id=?", (card_id,)).fetchone()
    assert row["task_run_id"] == rid, "the card must be linked to the run that produced it"
    assert row["status"] == "open"
    assert row["beneficiary"] == "Oscar"
    assert row["evidence_contract"] == "sqlite: SELECT * FROM work_wagers"


def test_a_stated_kill_condition_is_stored_verbatim(conn):
    rid = _run(conn)
    card_id = _open_work_card(
        conn, rid, Args("ship the door", "a row exists", kill="no second card in a week"), CONTRACT)

    row = conn.execute("SELECT kill_condition FROM work_wagers WHERE id=?", (card_id,)).fetchone()
    assert row["kill_condition"] == "no second card in a week"


def test_a_derived_kill_condition_says_it_is_derived(conn):
    """The one field the run surface does not ask for. Deriving it from the
    frozen acceptance test is allowed; passing the derivation off as something
    the operator wrote is not, so the provenance rides in the string itself."""
    rid = _run(conn)
    card_id = _open_work_card(conn, rid, Args("ship the door", "a row exists"), CONTRACT)

    kill = conn.execute(
        "SELECT kill_condition FROM work_wagers WHERE id=?", (card_id,)).fetchone()["kill_condition"]
    assert "derived at open, not stated" in kill
    assert "a row exists" in kill, "the derivation must quote the acceptance test it came from"


@pytest.mark.parametrize("missing", ["beneficiary", "observable_change", "evidence_source"])
def test_an_incomplete_contract_writes_no_card(conn, missing):
    """These three are gate BLOCKERS, so only a --force override reaches here
    without them. A card assembled from blanks would be a claim nobody made."""
    contract = {k: v for k, v in CONTRACT.items() if k != missing}
    rid = _run(conn)

    assert _open_work_card(conn, rid, Args("ship the door", "a row exists"), contract) is None
    assert conn.execute("SELECT COUNT(*) FROM work_wagers").fetchone()[0] == 0


def test_close_attaches_a_verification_receipt(conn):
    rid = _run(conn)
    card_id = _open_work_card(conn, rid, Args("ship the door", "a row exists"), CONTRACT)
    attach_artifact(conn, rid, [{"path_or_ref": "helicon/cli.py", "content_hash": "abc"}])
    accept_run(conn, rid, "accepted", note="it worked")

    _close_work_card(conn, rid, "accepted", "it worked")

    ev = conn.execute("SELECT * FROM work_evidence WHERE wager_id=?", (card_id,)).fetchall()
    assert len(ev) == 1
    assert ev[0]["kind"] == "taskrun-verification"
    assert ev[0]["reference"] == rid
    assert ev[0]["note"] == "it worked"


def test_close_does_not_resolve_the_card(conn):
    """A closed run says the artifact was accepted. A resolved card says the
    real-world change was observed. Auto-resolving here would stamp every card
    the instant work finished and destroy the only ratio the graph measures."""
    rid = _run(conn)
    card_id = _open_work_card(conn, rid, Args("ship the door", "a row exists"), CONTRACT)
    attach_artifact(conn, rid, [{"path_or_ref": "helicon/cli.py", "content_hash": "abc"}])
    accept_run(conn, rid, "accepted", note="it worked")

    _close_work_card(conn, rid, "accepted", "it worked")

    row = conn.execute("SELECT status, outcome FROM work_wagers WHERE id=?", (card_id,)).fetchone()
    assert row["status"] == "open"
    assert row["outcome"] is None


def test_a_closed_card_is_queued_for_an_outcome_ruling(conn):
    """`helicon run close` ends at 'reviewed', not 'verified'. The attention
    queue used to check only for 'verified', so it went silent on exactly the
    cards the CLI produces — at the moment they most need reading."""
    rid = _run(conn)
    _open_work_card(conn, rid, Args("ship the door", "a row exists"), CONTRACT)
    attach_artifact(conn, rid, [{"path_or_ref": "helicon/cli.py", "content_hash": "abc"}])
    accept_run(conn, rid, "accepted", note="it worked")
    _close_work_card(conn, rid, "accepted", "it worked")

    actions = {item["action"] for item in workgraph_attention(conn)}
    assert "attach_outcome_evidence" in actions
