"""Workgraph contracts: valuable output must be declared and evidenced."""
import pytest
import json

from helicon.db import init_db
from helicon.demo import seed
from helicon.wager import (WagerError, attach_evidence, compile_execution_prompt,
                           link_wager_to_run, open_wager, record_next_move, render_wager, resolve_wager,
                           review_declared_skill, trace_work_card, list_work_cards, measure_workgraph,
                           workgraph_attention, workgraph_learning)


@pytest.fixture
def conn(tmp_path):
    db = str(tmp_path / "helicon.db")
    seed(db)
    return init_db(db)


def _open(conn):
    return open_wager(
        conn,
        intent="stop sending maintenance prompts without a consequence",
        beneficiary="an agent-heavy solo builder",
        observable_change="the next action is backed by a declared outcome contract",
        evidence_contract="five real work decisions, including explicit rejections",
        kill_condition="the contract does not change the next action after five uses",
    )


def test_wager_freezes_the_outcome_contract_before_work(conn):
    wager_id = _open(conn)
    row = conn.execute("SELECT intent, beneficiary, status, outcome FROM work_wagers WHERE id=?", (wager_id,)).fetchone()
    assert row["intent"].startswith("stop sending")
    assert row["beneficiary"] == "an agent-heavy solo builder"
    assert row["status"] == "open" and row["outcome"] is None


def test_execution_evidence_is_not_automatically_an_outcome(conn):
    wager_id = _open(conn)
    attach_evidence(conn, wager_id, kind="test", reference="pytest tests/test_wager.py", note="contract tests pass")
    row = conn.execute("SELECT outcome, status FROM work_wagers WHERE id=?", (wager_id,)).fetchone()
    assert row["outcome"] is None and row["status"] == "open"
    resolve_wager(conn, wager_id, "unproven", ruling="the feature exists; five decisions have not occurred")
    row = conn.execute("SELECT outcome, status FROM work_wagers WHERE id=?", (wager_id,)).fetchone()
    assert row["outcome"] == "unproven" and row["status"] == "resolved"


def test_outcome_claims_need_a_human_ruling_and_a_receipt(conn):
    wager_id = _open(conn)
    with pytest.raises(WagerError, match="human ruling"):
        resolve_wager(conn, wager_id, "proven")
    attach_evidence(conn, wager_id, kind="user-feedback", reference="operator observation")
    with pytest.raises(WagerError, match="human ruling"):
        resolve_wager(conn, wager_id, "proven")
    resolve_wager(conn, wager_id, "proven", ruling="the observed change occurred")


def test_work_created_before_a_run_can_be_explicitly_linked_later(conn):
    import helicon.taskrun as taskrun
    wager_id = _open(conn)
    run_id = taskrun.open_run(conn, "ship a work graph", "build succeeds", task_class="feature")
    link_wager_to_run(conn, wager_id, run_id)
    assert trace_work_card(conn, wager_id)["task_run"]["id"] == run_id
    with pytest.raises(WagerError, match="already has a TaskRun"):
        link_wager_to_run(conn, wager_id, run_id)


def test_attention_queue_names_missing_edges_without_a_score(conn):
    import helicon.taskrun as taskrun
    wager_id = _open(conn)
    attention = workgraph_attention(conn)
    assert any(item["wager_id"] == wager_id and item["action"] == "link_run" for item in attention)
    run_id = taskrun.open_run(conn, "ship a work graph", "build succeeds", task_class="feature")
    link_wager_to_run(conn, wager_id, run_id)
    attention = workgraph_attention(conn)
    assert any(item["wager_id"] == wager_id and item["action"] == "freeze_context" for item in attention)


@pytest.mark.xfail(strict=True, reason=(
    "SALVAGE 2026-08-10, unruled defect in shipping code — not a port failure. "
    "The test asserts that a packet built from an objective matching nothing is "
    "empty, so the operator is told to review the query. In Mountain it freezes 11 "
    "items: taskrun._candidates delegates to snapshots._retrieve, whose semantic "
    "branch has NO relevance floor and always returns its nearest k. An agent is "
    "then handed 11 unrelated memories labelled keyword:<objective>. Fixing it "
    "means adding a similarity threshold to retrieval, which changes ranking "
    "everywhere and is not an additive salvage change. strict=True so this fails "
    "the moment the floor lands and the marker must be removed.")
)
def test_attention_queue_flags_a_frozen_but_empty_context_packet(conn):
    import helicon.taskrun as taskrun
    wager_id = _open(conn)
    run_id = taskrun.open_run(conn, "unrelated query", "build succeeds", task_class="feature")
    link_wager_to_run(conn, wager_id, run_id)
    taskrun.build_packet(conn, run_id, query="definitely-not-in-demo")
    attention = workgraph_attention(conn)
    assert any(item["wager_id"] == wager_id and item["action"] == "review_context_query" for item in attention)


def test_next_move_is_explicit_and_rejects_invalid_actions(conn):
    wager_id = _open(conn)
    move_id = record_next_move(conn, wager_id, "KILL", rationale="no beneficiary evidence")
    assert move_id.startswith("nm_")
    assert "next move:   KILL" in render_wager(conn, wager_id)
    with pytest.raises(WagerError):
        record_next_move(conn, wager_id, "POLISH", rationale="looks nicer")


def test_prompt_gate_abstains_without_an_accepted_build_move(conn):
    wager_id = _open(conn)
    record_next_move(conn, wager_id, "BUILD", rationale="the contract warrants a small slice")
    with pytest.raises(WagerError, match="abstains"):
        compile_execution_prompt(conn, wager_id)


def test_prompt_gate_compiles_the_wager_and_refuses_to_fake_outcome_proof(conn):
    wager_id = _open(conn)
    record_next_move(conn, wager_id, "BUILD", rationale="the contract warrants a small slice", status="accepted")
    prompt = compile_execution_prompt(conn, wager_id)
    assert "# Helicon Workgraph execution contract" in prompt
    assert "Evidence required to claim success" in prompt
    assert "Do not claim the outcome is proven merely because code, tests, or a diff exist." in prompt


def test_prompt_gate_refuses_non_execution_moves(conn):
    wager_id = _open(conn)
    record_next_move(conn, wager_id, "ASK", rationale="need user evidence first", status="accepted")
    with pytest.raises(WagerError, match="not agent execution"):
        compile_execution_prompt(conn, wager_id)


def test_mcp_prompt_gate_returns_a_real_abstention_or_an_approved_prompt(conn):
    from helicon.mcp_server import handle_tool_call
    wager_id = _open(conn)
    abstained = json.loads(handle_tool_call("helicon_prompt_gate", {"wager_id": wager_id}, conn))
    assert abstained["verdict"] == "abstain"
    record_next_move(conn, wager_id, "REPAIR", rationale="an accepted repair is required", status="accepted")
    approved = json.loads(handle_tool_call("helicon_prompt_gate", {"wager_id": wager_id}, conn))
    assert approved["verdict"] == "approved"
    assert "Approved action: REPAIR" in approved["prompt"]


def test_workgraph_trace_joins_work_to_task_context_memory_skills_and_evidence(conn):
    import helicon.taskrun as taskrun
    run_id = taskrun.open_run(
        conn, "make a governed prompt", "a contract is emitted", task_class="feature",
        model="qwen", harness="claude-code", skill_versions=["workgraph@1"],
    )
    taskrun.build_packet(conn, run_id, query="")
    taskrun.attach_artifact(conn, run_id, [{"path_or_ref": "helicon/wager.py", "content_hash": "abc", "observed_at": "now"}])
    wager_id = open_wager(
        conn, intent="join agent work to its context", beneficiary="operator",
        observable_change="one trace spans the real work chain", evidence_contract="inspect the trace",
        kill_condition="the trace invents unsupported links", task_run_id=run_id,
    )
    attach_evidence(conn, wager_id, kind="test", reference="tests/test_wager.py")
    trace = trace_work_card(conn, wager_id)
    assert trace["task_run"]["id"] == run_id
    assert trace["skills"] == ["workgraph@1"]
    assert trace["context_packet"]["included_memory_items"]
    assert trace["artifacts"][0]["path_or_ref"] == "helicon/wager.py"
    assert trace["execution_evidence"][0]["kind"] == "test"
    assert [event["at"] for event in trace["timeline"]] == sorted(event["at"] for event in trace["timeline"])
    assert {"work-opened", "run-opened", "context-frozen", "artifact-attached", "execution-evidence"}.issubset(
        {event["kind"] for event in trace["timeline"]}
    )
    assert list_work_cards(conn)[0]["id"] == wager_id
    assert measure_workgraph(conn)["declared_skills"] >= 1


def test_declared_skill_review_hashes_the_actual_instruction_file_and_closes_that_edge(conn, tmp_path):
    import helicon.taskrun as taskrun
    run_id = taskrun.open_run(conn, "review skills", "snapshot instructions", harness="codex",
                              skill_versions=["workgraph@1"])
    wager_id = open_wager(conn, intent="bind skill instructions to the run", beneficiary="operator",
                          observable_change="the exact reviewed instructions are recorded",
                          evidence_contract="a local content hash", kill_condition="the source is unrelated",
                          task_run_id=run_id)
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("---\nname: workgraph\n---\n# Work graph\n", encoding="utf-8")
    result = review_declared_skill(conn, wager_id, skill_version="workgraph@1", source_path=str(skill_file))
    assert result["content_hash"]
    trace = trace_work_card(conn, wager_id)
    assert trace["skill_reviews"][0]["skill_version"] == "workgraph@1"
    assert not any(item["action"] == "review_declared_skills" for item in workgraph_attention(conn))
    assert measure_workgraph(conn)["reviewed_skill_versions"] == 1
    with pytest.raises(WagerError, match="not declared"):
        review_declared_skill(conn, wager_id, skill_version="unknown@1", source_path=str(skill_file))


def test_workgraph_api_returns_cards_and_measured_coverage(conn, monkeypatch):
    import asyncio
    from helicon.api import workgraph

    wager_id = _open(conn)
    monkeypatch.setattr(workgraph, "_conn", lambda: conn)
    response = asyncio.run(workgraph.work_cards())
    assert response["cards"][0]["id"] == wager_id
    assert response["measurement"]["work_cards"] >= 1
    attention = asyncio.run(workgraph.work_attention())
    assert attention["attention"][0]["action"] == "link_run"


def test_mcp_attention_reports_missing_edges(conn):
    from helicon.mcp_server import handle_tool_call
    _open(conn)
    response = json.loads(handle_tool_call("helicon_workgraph_attention", {}, conn))
    assert response["attention"][0]["action"] == "link_run"


def test_learning_withholds_recommendations_until_real_resolved_outcomes_accumulate(conn):
    import helicon.taskrun as taskrun
    run_id = taskrun.open_run(conn, "learn safely", "test", model="gpt-5", harness="codex", skill_versions=["workgraph@1"])
    wager_id = open_wager(conn, intent="learn safely", beneficiary="operator", observable_change="record", evidence_contract="receipt", kill_condition="false learning", task_run_id=run_id)
    attach_evidence(conn, wager_id, kind="human-observation", reference="local")
    resolve_wager(conn, wager_id, "proven", ruling="observed once")
    learning = workgraph_learning(conn)
    assert learning["resolved_work_cards"] == 1
    assert learning["recommendations_withheld"] is True
    assert learning["observations"]["harness"][0]["verdict"] == "insufficient evidence"


def test_execution_receipts_cannot_prove_a_human_outcome(conn):
    wager_id = _open(conn)
    attach_evidence(conn, wager_id, kind="taskrun-verification", reference="tr_real")
    with pytest.raises(WagerError, match="not only execution evidence"):
        resolve_wager(conn, wager_id, "proven", ruling="tests passed")
    attach_evidence(conn, wager_id, kind="user-feedback", reference="operator observed the change")
    resolve_wager(conn, wager_id, "proven", ruling="beneficiary observed the change")


def test_all_five_pre_execution_fields_are_required(conn):
    with pytest.raises(WagerError, match="beneficiary"):
        open_wager(conn, intent="x", beneficiary="", observable_change="x", evidence_contract="x", kill_condition="x")
