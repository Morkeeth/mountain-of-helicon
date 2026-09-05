"""Local context delivery through the real MCP dispatch, with denial cases."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from helicon.context_history import ContextHistory
from helicon.context_packet import ContextPackets, PacketError, packet_store_for_project
from helicon.mcp_server import REMOTE_TOOL_NAMES, TOOLS, handle_rpc_message


@pytest.fixture
def setup(tmp_path):
    project = (tmp_path / "project").resolve()
    project.mkdir()
    (project / ".git").mkdir()
    source = project / "AGENTS.md"
    source.write_text("Use the current greeting.\n")
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    review = {"schema": "helicon.context-review/1", "project": str(project),
              "observed_at": "2026-09-05T00:00:00+00:00", "sources": [
                  {"id": "source", "path": str(source), "sha256": sha, "status": "available"}],
              "findings": [], "coverage": {"checks": []}}
    state = tmp_path.resolve() / "state"
    snapshot = ContextHistory(state / "reviews").save(review)
    store = ContextPackets(state / "packets", state / "reviews")
    recipient = {"run_id": "fixture-run", "provider": "codex", "project": str(project)}
    return store, snapshot, source, recipient


def test_issue_inspect_consume_and_independent_behavior_are_distinct(setup):
    store, snapshot, source, recipient = setup
    packet = store.create(snapshot["id"], ["source"], recipient)
    metadata = store.inspect(packet["id"], recipient)
    assert metadata["state"] == "issued"
    assert metadata["consumption"] is None
    assert metadata["behavior_status"] == "unverified"
    assert "content" not in metadata["sources"][0]
    assert not (store.root / "consumed").exists()
    assert not (store.root / "behavior").exists()
    result = store.consume(packet["id"], recipient)
    assert result["packet"]["sources"][0]["content"] == source.read_text()
    assert result["packet"]["review_sha256"] == snapshot["sha256"]
    assert result["consumption"]["source_hashes"]["source"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert result["consumption"]["transport"] == "local-library"
    assert store.consume(packet["id"], recipient)["consumption"] == result["consumption"]
    assert store.inspect(packet["id"], recipient)["behavior_status"] == "unverified"
    artifact = source.parent / "greeting.txt"
    artifact.write_text("Hello from the controlled fixture.\n")
    proof = store.attach_behavior(packet["id"], recipient, str(artifact), "fixture-reviewer",
                                  "Read greeting.txt and compared its wording with the instruction.", "supported")
    assert proof["artifact_sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert proof["verification"] == "caller-supplied reviewer observation"
    assert store.inspect(packet["id"], recipient)["behavior"][0]["artifact_current"]
    artifact.write_text("Changed after reviewer observation")
    assert not store.inspect(packet["id"], recipient)["behavior"][0]["artifact_current"]


def test_stale_source_is_refused_before_issue_and_consumption(setup):
    store, snapshot, source, recipient = setup
    packet = store.create(snapshot["id"], ["source"], recipient)
    source.write_text("Changed after the review")
    with pytest.raises(PacketError, match="changed"):
        store.create(snapshot["id"], ["source"], recipient)
    with pytest.raises(PacketError, match="changed"):
        store.consume(packet["id"], recipient)
    assert not (store.root / "consumed").exists()
    assert store.inspect(packet["id"], recipient)["state"] == "issued"


@pytest.mark.parametrize("field,value", [("run_id", "other-run"), ("provider", "other-provider")])
def test_wrong_recipient_cannot_inspect_or_consume(setup, field, value):
    store, snapshot, source, recipient = setup
    packet = store.create(snapshot["id"], ["source"], recipient)
    wrong = dict(recipient, **{field: value})
    for operation in (store.inspect, store.consume):
        with pytest.raises(PacketError, match="recipient"):
            operation(packet["id"], wrong)
    assert not (store.root / "consumed").exists()


def test_sources_are_explicit_and_global_sources_never_enter_project_packet(setup):
    store, snapshot, source, recipient = setup
    global_source = source.parent.parent / "global.md"
    global_source.write_text("Private global context")
    review = snapshot["review"]
    review["sources"].append({"id": "global", "path": str(global_source), "sha256": hashlib.sha256(global_source.read_bytes()).hexdigest(), "status": "available"})
    snapshot = store.history.save(review)
    packet = store.create(snapshot["id"], ["source"], recipient)
    assert len(packet["sources"]) == 1
    for ids in ([], ["global"], ["source", "source"], ["unknown"]):
        with pytest.raises(PacketError):
            store.create(snapshot["id"], ids, recipient)


def test_symlink_swap_escape_and_in_project_storage_are_denied(setup):
    store, snapshot, source, recipient = setup
    packet = store.create(snapshot["id"], ["source"], recipient)
    elsewhere = source.parent.parent / "outside.md"
    elsewhere.write_text(source.read_text())
    source.unlink()
    source.symlink_to(elsewhere)
    with pytest.raises(PacketError, match="Symlink"):
        store.consume(packet["id"], recipient)
    wrong_store = ContextPackets(source.parent / "state", store.history.root)
    with pytest.raises(PacketError, match="outside the project"):
        wrong_store.create(snapshot["id"], ["source"], recipient)


def test_no_behavior_without_consumption_or_self_attestation(setup):
    store, snapshot, source, recipient = setup
    packet = store.create(snapshot["id"], ["source"], recipient)
    artifact = source.parent / "greeting.txt"
    artifact.write_text("Hello")
    with pytest.raises(PacketError, match="Consume"):
        store.attach_behavior(packet["id"], recipient, str(artifact), "reviewer", "Read artifact", "supported")
    store.consume(packet["id"], recipient)
    with pytest.raises(PacketError, match="separate named reviewer"):
        store.attach_behavior(packet["id"], recipient, str(artifact), recipient["run_id"], "Read artifact", "supported")
    with pytest.raises(PacketError, match="separate from"):
        store.attach_behavior(packet["id"], recipient, str(source), "reviewer", "Echo", "supported")


def test_mcp_local_consume_and_remote_denial_use_real_dispatch(setup, monkeypatch):
    import helicon.context_packet as module
    import helicon.mcp_server as server
    store, snapshot, source, recipient = setup
    packet = store.create(snapshot["id"], ["source"], recipient)
    monkeypatch.setattr(module, "packet_store_for_project", lambda project, config: store)
    monkeypatch.setattr(server, "load_config", lambda: {})
    names = {t["name"] for t in TOOLS}
    for name in ("helicon_context_packet_inspect", "helicon_context_packet_consume"):
        assert name in names and name not in REMOTE_TOOL_NAMES
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": name, "arguments": {"packet_id": packet["id"], "recipient": recipient}}}
        denied = handle_rpc_message(request, None, allowed_tool_names=REMOTE_TOOL_NAMES)
        assert denied["error"]["code"] == -32602
        assert not (store.root / "consumed").exists()
        response = handle_rpc_message(request, None)
        content = json.loads(response["result"]["content"][0]["text"])
        assert "error" not in content
    assert content["packet"]["sources"][0]["content"] == source.read_text()
    assert content["consumption"]["transport"] == "local-stdio"
    assert content["behavior_status"] == "unverified"


def test_project_configuration_matches_api_state_paths(tmp_path, monkeypatch):
    project = (tmp_path / "project").resolve()
    project.mkdir()
    state = tmp_path.resolve() / "state"
    monkeypatch.setenv("HELICON_HOME", str(state))
    config = {"context_review": {"projects": [{"id": "example", "path": str(project), "name": "Example"}]}}
    store = packet_store_for_project(str(project), config)
    base = state / "context-review" / hashlib.sha256(str(project).encode()).hexdigest()[:24]
    assert store.root == base / "packets"
    assert store.history.root == base / "reviews"
    assert not state.exists()
    with pytest.raises(PacketError, match="not in"):
        packet_store_for_project(str(tmp_path.resolve()), config)


def test_packet_hash_tamper_refused_and_state_files_private(setup):
    store, snapshot, source, recipient = setup
    packet = store.create(snapshot["id"], ["source"], recipient)
    path = store.root / "issued" / (packet["id"] + ".json")
    assert path.stat().st_mode & 0o077 == 0
    data = json.loads(path.read_text())
    data["sources"][0]["content"] = "Tampered"
    path.write_text(json.dumps(data))
    with pytest.raises(PacketError, match="invalid"):
        store.consume(packet["id"], recipient)


def test_storage_child_symlink_and_fifo_source_are_denied(setup):
    store, snapshot, source, recipient = setup
    packet = store.create(snapshot["id"], ["source"], recipient)
    other = store.root.parent / "other"
    other.mkdir()
    (store.root / "consumed").symlink_to(other, target_is_directory=True)
    with pytest.raises(PacketError, match="child must not"):
        store.consume(packet["id"], recipient)
    assert not list(other.iterdir())
    (store.root / "consumed").unlink()
    source.unlink()
    os.mkfifo(source)
    with pytest.raises(PacketError, match="unavailable"):
        store.consume(packet["id"], recipient)


def test_actual_stdio_server_consumes_frozen_project_packet(setup, monkeypatch):
    _, snapshot, source, recipient = setup
    state = source.parent.parent / "stdio-state"
    monkeypatch.setenv("HELICON_HOME", str(state))
    config = {"db_path": str(state / "fixture.db"), "context_review": {"projects": [
        {"id": "fixture", "path": recipient["project"], "name": "Controlled fixture"}]}}
    store = packet_store_for_project(recipient["project"], config)
    saved = store.history.save(snapshot["review"])
    packet = store.create(saved["id"], ["source"], recipient)
    config_path = state / "fixture-config.json"
    config_path.write_text(json.dumps(config))
    env = dict(os.environ, HELICON_CONFIG=str(config_path))
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "helicon_context_packet_consume", "arguments": {
                "packet_id": packet["id"], "recipient": recipient}}},
    ]
    completed = subprocess.run([sys.executable, "-m", "helicon.mcp_server"],
                               input="".join(json.dumps(m) + "\n" for m in messages),
                               capture_output=True, text=True, env=env, timeout=15)
    assert completed.returncode == 0, completed.stderr
    replies = [json.loads(line) for line in completed.stdout.splitlines()]
    response = next(r for r in replies if r["id"] == 2)
    consumed = json.loads(response["result"]["content"][0]["text"])
    assert consumed["packet"]["sources"][0]["content"] == source.read_text()
    assert consumed["consumption"]["transport"] == "local-stdio"
    assert store.inspect(packet["id"], recipient)["state"] == "consumed"
    assert store.inspect(packet["id"], recipient)["behavior_status"] == "unverified"
