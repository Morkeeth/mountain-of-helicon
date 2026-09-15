import pytest

from helicon.correction_transfer import (
    AUTHORED_EXAMPLE,
    CorrectionTransferStore,
    TransferError,
    word_delta,
)


def propose(store, **changes):
    fields = {key: value for key, value in AUTHORED_EXAMPLE.items() if key != "cases"}
    fields.update(changes)
    return store.propose(actor="human:fixture", **fields)


def test_word_delta_and_authorship_are_visible(tmp_path):
    store = CorrectionTransferStore(tmp_path)
    proposal = propose(store)

    assert proposal["status"] == "proposed"
    assert proposal["word_delta"] == [
        {"kind": "removed", "text": "shipped"},
        {"kind": "added", "text": "built"},
    ]
    assert proposal["reason_authority"] == {
        "explicit_instruction": "human-authored",
        "inferred_reason": "agent-inferred; not an instruction",
    }
    assert proposal["events"][0]["detail"] == "No later attempt changed."


def test_accepted_rule_transfers_only_to_complete_scope(tmp_path):
    store = CorrectionTransferStore(tmp_path)
    accepted = store.decide(propose(store)["id"], "accept", "human:fixture")
    comparison = store.compare(AUTHORED_EXAMPLE["cases"])

    relevant, unrelated = comparison["cases"]
    assert relevant["frozen_baseline"] == "We shipped the correction history."
    assert relevant["result"] == "We built the correction history."
    assert relevant["applied_rules"][0]["rule_id"] == accepted["id"]
    assert unrelated["result"] == unrelated["frozen_baseline"]
    assert unrelated["applied_rules"] == []
    assert "Personal benefit" in comparison["claim_limit"]


def test_rejected_and_undone_rules_do_not_transfer(tmp_path):
    store = CorrectionTransferStore(tmp_path)
    proposal = propose(store)
    store.decide(proposal["id"], "reject", "human:fixture")
    assert not store.compare(AUTHORED_EXAMPLE["cases"])["cases"][0]["changed"]
    store.undo(proposal["id"], "human:fixture")
    assert store.get(proposal["id"])["status"] == "undone"

    accepted = store.decide(propose(store)["id"], "accept", "human:fixture")
    store.undo(accepted["id"], "human:fixture")
    assert not store.compare(AUTHORED_EXAMPLE["cases"])["cases"][0]["changed"]


def test_scope_can_change_before_acceptance(tmp_path):
    store = CorrectionTransferStore(tmp_path)
    proposal = propose(store)
    changed = store.change_scope(
        proposal["id"],
        {"project": "mountain-of-helicon", "task": "release-note"},
        "human:fixture",
    )
    assert changed["scope"]["task"] == "release-note"
    store.decide(proposal["id"], "accept", "human:fixture")
    relevant, release = store.compare(AUTHORED_EXAMPLE["cases"])["cases"]
    assert not relevant["changed"]
    assert release["changed"]


def test_accepted_rule_scope_is_immutable_and_supersession_is_undoable(tmp_path):
    store = CorrectionTransferStore(tmp_path)
    first = store.decide(propose(store)["id"], "accept", "human:fixture")
    with pytest.raises(TransferError, match="immutable"):
        store.change_scope(first["id"], {"task": "all"}, "human:fixture")

    second = propose(
        store,
        scope={"project": "mountain-of-helicon", "task": "release-note"},
        supersedes=first["id"],
    )
    store.decide(second["id"], "accept", "human:fixture")
    assert store.get(first["id"])["status"] == "superseded"
    relevant, release = store.compare(AUTHORED_EXAMPLE["cases"])["cases"]
    assert not relevant["changed"]
    assert release["changed"]

    store.undo(second["id"], "human:fixture")
    assert store.get(first["id"])["status"] == "accepted"
    relevant, release = store.compare(AUTHORED_EXAMPLE["cases"])["cases"]
    assert relevant["changed"]
    assert not release["changed"]


def test_operation_must_reproduce_edit_exactly(tmp_path):
    store = CorrectionTransferStore(tmp_path)
    with pytest.raises(TransferError, match="exactly reproduce"):
        propose(store, operation={"find": "shipped", "replace": "launched"})


def test_empty_store_read_is_non_mutating(tmp_path):
    state = tmp_path / "absent"
    assert CorrectionTransferStore(state).list() == []
    assert not state.exists()
