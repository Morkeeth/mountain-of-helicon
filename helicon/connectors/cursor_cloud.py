"""Privacy-bounded ingestion for Cursor Cloud agent export bundles.

The Cursor Cloud diagnostics export contains full prompts, reasoning, terminal
commands, file contents, and tool output. The default connector stores only a
deterministic structural run summary. Operators may explicitly opt into user
and final-assistant text; reasoning and tool payloads are never ingested.
"""

import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from glob import glob

from helicon.models import ConnectorResult


_MAX_JSON_BYTES = 50 * 1024 * 1024
_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"']+"),
    re.compile(r"(?i)\b(?:ghp|github_pat)_[A-Za-z0-9_]{16,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(https?://x-access-token:)[^@\s]+(@github\.com)"),
)


def _read_json(path: str) -> dict:
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > _MAX_JSON_BYTES:
            return {}
        with open(path, encoding="utf-8") as fh:
            value = json.load(fh)
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _iso_from_ms(value) -> str:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _int(value, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _redact_text(text: str) -> str:
    text = str(text or "")
    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 2:
            text = pattern.sub(r"\1[REDACTED]\2", text)
        elif pattern.groups == 1:
            text = pattern.sub(r"\1[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def _index_paths(root: str) -> list[str]:
    direct = os.path.join(root, "index.json")
    if os.path.isfile(direct):
        return [direct]
    return sorted(glob(os.path.join(root, "**", "index.json"), recursive=True))


def _latest_agents(root: str) -> dict[str, tuple[dict, str]]:
    """Return the newest exported snapshot and batch directory per cloud run."""
    latest: dict[str, tuple[dict, str]] = {}
    for index_path in _index_paths(root):
        batch_dir = os.path.dirname(index_path)
        for agent in _read_json(index_path).get("agents", []):
            if not isinstance(agent, dict):
                continue
            bc_id = agent.get("bcId")
            if not isinstance(bc_id, str) or not bc_id:
                continue
            previous = latest.get(bc_id)
            updated = _int(agent.get("updatedAtMs"))
            previous_updated = _int(previous[0].get("updatedAtMs")) if previous else -1
            if previous is None or updated >= previous_updated:
                latest[bc_id] = (agent, batch_dir)
    return latest


def _tool_failed(message: dict) -> bool:
    result = message.get("tool_result")
    if not isinstance(result, dict):
        return False
    value = result.get("value")
    if not isinstance(value, dict):
        return False
    exit_code = value.get("exitCode")
    return (
        (isinstance(exit_code, int) and exit_code != 0)
        or value.get("applyFailed") is True
        or value.get("success") is False
    )


def _bounded_text(messages: list[dict], max_chars: int) -> list[str]:
    """Opt-in transcript text: user/final prose only, never thoughts or tools."""
    snippets = []
    remaining = max(0, max_chars)
    for message in messages:
        if remaining <= 0 or not isinstance(message, dict):
            break
        role = message.get("role")
        text = message.get("text")
        if role not in {"user", "assistant"} or not isinstance(text, str) or not text.strip():
            continue
        clean = _redact_text(text.strip())
        clean = clean[:remaining]
        snippets.append(f"{role.title()}: {clean}")
        remaining -= len(clean)
    return snippets


def _run_result(agent: dict, batch_dir: str, config: dict) -> ConnectorResult:
    bc_id = agent["bcId"]
    run_dir = os.path.join(batch_dir, bc_id)
    transcript = _read_json(os.path.join(run_dir, "transcript.json"))
    diff = _read_json(os.path.join(run_dir, "diff-metadata.json"))
    events_doc = _read_json(os.path.join(run_dir, "events.json"))

    messages = transcript.get("messages", [])
    if not isinstance(messages, list):
        messages = []
    messages = [message for message in messages if isinstance(message, dict)]

    roles = Counter(message.get("role", "unknown") for message in messages)
    tools = Counter()
    failed_tools = 0
    completed_tool_results = 0
    for message in messages:
        if message.get("role") != "tool":
            continue
        tool_name = message.get("tool_name")
        if isinstance(tool_name, str) and tool_name:
            tools[tool_name] += 1
        if isinstance(message.get("tool_result"), dict):
            completed_tool_results += 1
            failed_tools += int(_tool_failed(message))

    events = events_doc.get("events", [])
    if not isinstance(events, list):
        events = []
    event_kinds = Counter(
        event.get("kind") for event in events
        if isinstance(event, dict) and isinstance(event.get("kind"), str)
    )

    started_ms = _int(agent.get("createdAtMs"))
    ended_ms = _int(agent.get("lastMessageActivityAtMs") or agent.get("updatedAtMs"))
    duration_seconds = max(0, (ended_ms - started_ms) // 1000) if started_ms and ended_ms else 0
    tool_summary = ", ".join(f"{name} ×{count}" for name, count in sorted(tools.items())) or "none"
    event_summary = ", ".join(f"{name} ×{count}" for name, count in sorted(event_kinds.items())) or "none"

    lines = [
        f"Cursor Cloud run: {agent.get('name') or bc_id}",
        f"Repository: {agent.get('repoUrl') or 'unknown'}",
        f"Branch: {agent.get('branchName') or 'unknown'}",
        f"Status: {agent.get('status') or 'unknown'}; setup: {agent.get('setupStatus') or 'unknown'}",
        f"Model: {agent.get('originalModelName') or 'unknown'}",
        f"Messages: {len(messages)} ({roles.get('user', 0)} user, {roles.get('assistant', 0)} assistant, {roles.get('tool', 0)} tool)",
        f"Tools: {tool_summary}",
        f"Completed tool results: {completed_tool_results}; observed failures: {failed_tools}",
        f"Events: {event_summary}",
        (
            f"Change: {_int(diff.get('filesChanged'))} files, "
            f"+{_int(diff.get('linesAdded'))} -{_int(diff.get('linesRemoved'))}; "
            f"PR: {diff.get('prStatus') or 'none'}; merged: {bool(diff.get('isPrMerged'))}"
        ),
    ]
    if config.get("include_text") is True:
        max_chars = _int(config.get("max_text_chars"), 6000)
        text = _bounded_text(messages, min(max(max_chars, 0), 50_000))
        if text:
            lines.extend(["", "Opt-in conversation text:", *text])

    return ConnectorResult(
        source="cursor-cloud",
        source_ref=f"cursor/cloud-agent/{bc_id}",
        type="session",
        title=f"Cursor Cloud: {(agent.get('name') or bc_id)[:80]}",
        content="\n".join(lines),
        created_at=_iso_from_ms(started_ms),
        tags=["cursor", "cloud-agent", str(agent.get("status") or "unknown").lower()],
        metadata={
            "bc_id": bc_id,
            "repo_url": agent.get("repoUrl") or "",
            "branch": agent.get("branchName") or "",
            "status": agent.get("status") or "",
            "setup_status": agent.get("setupStatus") or "",
            "model": agent.get("originalModelName") or "",
            "message_count": len(messages),
            "prompt_count": roles.get("user", 0),
            "tool_counts": dict(sorted(tools.items())),
            "failed_tool_count": failed_tools,
            "duration_seconds": duration_seconds,
            "files_changed": _int(diff.get("filesChanged")),
            "lines_added": _int(diff.get("linesAdded")),
            "lines_removed": _int(diff.get("linesRemoved")),
            "pr_status": diff.get("prStatus") or "",
            "is_pr_merged": bool(diff.get("isPrMerged")),
            "event_kinds": dict(sorted(event_kinds.items())),
            "includes_conversation_text": config.get("include_text") is True,
        },
    )


def scan(config: dict) -> list[ConnectorResult]:
    export_dir = os.path.abspath(os.path.expanduser(config.get("export_dir", "")))
    if not config.get("export_dir") or not os.path.isdir(export_dir):
        return []

    results = []
    for _, (agent, batch_dir) in sorted(_latest_agents(export_dir).items()):
        try:
            results.append(_run_result(agent, batch_dir, config))
        except (TypeError, ValueError, OSError):
            # One malformed run cannot darken every other exported run.
            continue
    return results
