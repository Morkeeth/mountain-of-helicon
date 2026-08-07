import json

from helicon.connectors import cursor_cloud


BC_ID = "bc-00000000-0000-0000-0000-000000000001"


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _agent(name, updated):
    return {
        "bcId": BC_ID,
        "name": name,
        "branchName": "cursor/fixture-e0ab",
        "repoUrl": "github.com/org/repo",
        "status": "FINISHED",
        "setupStatus": "INSTALL_SUCCEEDED",
        "source": "web",
        "originalModelName": "test-model",
        "createdAtMs": 1_785_932_542_715,
        "updatedAtMs": updated,
        "lastMessageActivityAtMs": 1_785_932_602_715,
    }


def _export(root):
    old = root / "2026-01-01-old"
    new = root / "2026-01-02-new"
    _write(old / "index.json", {"agents": [_agent("Old snapshot", 1)]})
    _write(new / "index.json", {"agents": [_agent("Current run", 2)]})

    run = new / BC_ID
    _write(run / "transcript.json", {
        "messages": [
            {"role": "user", "text": "Private prompt; key sk-abcdefghijklmnopqrstuvwxyz"},
            {"role": "assistant", "thinking": "Never store this private reasoning"},
            {"role": "assistant", "text": "Final response without private reasoning"},
            {
                "role": "assistant",
                "tool_calls": [{
                    "tool_call_id": "turn-0:step:1:tool",
                    "tool_name": "run_terminal_cmd",
                    "tool_args": {"command": "git remote -v"},
                }],
            },
            {
                "role": "tool",
                "tool_call_id": "turn-0:step:1:tool",
                "tool_name": "run_terminal_cmd",
                "tool_args": {"command": "git remote -v"},
                "tool_result": {
                    "resultType": "runTerminalCommandV2Result",
                    "value": {
                        "output": "https://x-access-token:topsecret@github.com/org/repo",
                        "exitCode": 1,
                    },
                },
            },
            {
                "role": "tool",
                "tool_call_id": "turn-0:step:2:tool",
                "tool_name": "read_file",
            },
        ],
    })
    _write(run / "diff-metadata.json", {
        "bcId": BC_ID,
        "prUrl": "https://github.com/org/repo/pull/1",
        "prStatus": "DRAFT",
        "isPrMerged": False,
        "linesAdded": 10,
        "linesRemoved": 2,
        "filesChanged": 1,
    })
    _write(run / "events.json", {
        "bcId": BC_ID,
        "count": 2,
        "events": [
            {
                "publicId": "evt-1",
                "createdAtMs": 1_785_932_555_619,
                "category": "agent_setup",
                "logLevel": "info",
                "kind": "setup_completed",
                "title": "Environment setup completed",
            },
            {
                "publicId": "evt-2",
                "createdAtMs": 1_785_932_582_579,
                "category": "agent_run",
                "logLevel": "info",
                "kind": "pr_created",
                "title": "Draft pull request created",
            },
        ],
    })
    return new


def test_cursor_cloud_scan_is_metadata_only_and_uses_latest_snapshot(tmp_path):
    _export(tmp_path)

    results = cursor_cloud.scan({"export_dir": str(tmp_path)})

    assert len(results) == 1
    result = results[0]
    assert result.source == "cursor-cloud"
    assert result.source_ref == f"cursor/cloud-agent/{BC_ID}"
    assert result.title == "Cursor Cloud: Current run"
    assert "Messages: 6 (1 user, 3 assistant, 2 tool)" in result.content
    assert "Tools: read_file ×1, run_terminal_cmd ×1" in result.content
    assert "Completed tool results: 1; observed failures: 1" in result.content
    assert "Change: 1 files, +10 -2; PR: DRAFT; merged: False" in result.content
    assert "Private prompt" not in result.content
    assert "Final response" not in result.content
    assert "private reasoning" not in result.content
    assert "topsecret" not in result.content
    assert "git remote" not in result.content
    assert result.created_at == "2026-08-05T12:22:22.715000+00:00"
    assert result.metadata["prompt_count"] == 1
    assert result.metadata["tool_counts"] == {"read_file": 1, "run_terminal_cmd": 1}
    assert result.metadata["failed_tool_count"] == 1
    assert result.metadata["duration_seconds"] == 60
    assert result.metadata["event_kinds"] == {"pr_created": 1, "setup_completed": 1}
    assert result.metadata["includes_conversation_text"] is False


def test_cursor_cloud_text_ingestion_is_explicit_bounded_and_redacted(tmp_path):
    _export(tmp_path)

    [result] = cursor_cloud.scan({
        "export_dir": str(tmp_path),
        "include_text": True,
        "max_text_chars": 2000,
    })

    assert "Opt-in conversation text:" in result.content
    assert "User: Private prompt; key [REDACTED]" in result.content
    assert "Assistant: Final response without private reasoning" in result.content
    assert "Never store this private reasoning" not in result.content
    assert "topsecret" not in result.content
    assert "git remote" not in result.content
    assert result.metadata["includes_conversation_text"] is True


def test_cursor_cloud_accepts_a_single_batch_directory(tmp_path):
    batch = _export(tmp_path)

    results = cursor_cloud.scan({"export_dir": str(batch)})

    assert len(results) == 1
    assert results[0].metadata["bc_id"] == BC_ID


def test_cursor_cloud_missing_or_malformed_exports_are_empty(tmp_path):
    assert cursor_cloud.scan({}) == []
    assert cursor_cloud.scan({"export_dir": str(tmp_path / "missing")}) == []

    _write(tmp_path / "index.json", ["not", "an", "object"])
    assert cursor_cloud.scan({"export_dir": str(tmp_path)}) == []
