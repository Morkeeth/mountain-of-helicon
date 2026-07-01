import json
import os
import re
from glob import glob
from datetime import datetime

from glaze.models import ConnectorResult


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm = {}
    for line in parts[1].strip().split("\n"):
        line = line.strip()
        if ":" in line and not line.startswith("-"):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",") if v.strip()]
            fm[key] = val
    body = parts[2].strip()
    return fm, body


def scan_sessions_index(config: dict) -> list[ConnectorResult]:
    index_path = config.get("sessions_index", "")
    if not index_path or not os.path.exists(index_path):
        return []

    with open(index_path) as f:
        data = json.load(f)

    results = []
    for entry in data.get("entries", []):
        session_id = entry.get("sessionId", "")
        summary = entry.get("summary", "")
        if not summary:
            continue

        created = entry.get("created", "")
        msg_count = entry.get("messageCount", 0)

        results.append(ConnectorResult(
            source="claude-code",
            source_ref=f"session_{session_id[:8]}",
            type="session",
            title=summary,
            content=f"Session: {summary}\nMessages: {msg_count}\nFirst prompt: {entry.get('firstPrompt', '')[:200]}",
            created_at=created,
            tags=["session"],
            metadata={
                "session_id": session_id,
                "message_count": msg_count,
                "git_branch": entry.get("gitBranch", ""),
                "project_path": entry.get("projectPath", ""),
            },
        ))

    return results


def scan_jsonl(config: dict) -> list[ConnectorResult]:
    jsonl_dir = config.get("jsonl_dir", "")
    if not jsonl_dir or not os.path.exists(jsonl_dir):
        return []

    results = []
    jsonl_files = glob(os.path.join(jsonl_dir, "*.jsonl"))

    for filepath in jsonl_files:
        session_id = os.path.basename(filepath).replace(".jsonl", "")[:8]
        try:
            with open(filepath) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    entry_type = obj.get("type")
                    if entry_type != "assistant":
                        continue

                    message = obj.get("message", {})
                    content = message.get("content", [])
                    timestamp = obj.get("timestamp", "")

                    if not isinstance(content, list):
                        continue

                    for block in content:
                        if block.get("type") != "tool_use":
                            continue

                        tool_name = block.get("name", "")
                        tool_input = block.get("input", {})

                        if tool_name == "Write":
                            file_path = tool_input.get("file_path", "")
                            file_content = tool_input.get("content", "")
                            if not file_path:
                                continue
                            filename = os.path.basename(file_path)
                            snippet = file_content[:500] if file_content else ""
                            results.append(ConnectorResult(
                                source="claude-code",
                                source_ref=f"session_{session_id}",
                                type="file_created",
                                title=f"Created: {filename}",
                                content=f"File: {file_path}\n\n{snippet}",
                                created_at=timestamp,
                                tags=_tags_from_path(file_path),
                                metadata={"file_path": file_path, "tool": "Write"},
                            ))

                        elif tool_name == "Edit":
                            file_path = tool_input.get("file_path", "")
                            old_string = tool_input.get("old_string", "")[:200]
                            new_string = tool_input.get("new_string", "")[:200]
                            if not file_path:
                                continue
                            filename = os.path.basename(file_path)
                            results.append(ConnectorResult(
                                source="claude-code",
                                source_ref=f"session_{session_id}",
                                type="code",
                                title=f"Edited: {filename}",
                                content=f"File: {file_path}\n- {old_string}\n+ {new_string}",
                                created_at=timestamp,
                                tags=_tags_from_path(file_path),
                                metadata={"file_path": file_path, "tool": "Edit"},
                            ))
        except Exception:
            continue

    return results


def scan_memory(config: dict) -> list[ConnectorResult]:
    memory_dir = config.get("memory_dir", "")
    if not memory_dir or not os.path.exists(memory_dir):
        return []

    results = []
    for filepath in glob(os.path.join(memory_dir, "*.md")):
        filename = os.path.basename(filepath)
        if filename == "MEMORY.md":
            continue

        try:
            with open(filepath) as f:
                text = f.read()
        except Exception:
            continue

        fm, body = parse_frontmatter(text)
        name = fm.get("name", filename.replace(".md", ""))
        description = fm.get("description", "")
        mem_type = fm.get("type", "")
        if isinstance(mem_type, list):
            mem_type = mem_type[0] if mem_type else ""
        if not mem_type:
            meta = fm.get("metadata", "")
            if isinstance(meta, str) and "type" in meta:
                pass

        mtime = os.path.getmtime(filepath)
        created = datetime.fromtimestamp(mtime).isoformat()

        tags = ["memory"]
        if mem_type:
            tags.append(mem_type)
        if filename.startswith("feedback_"):
            tags.append("feedback")
        elif filename.startswith("project_"):
            tags.append("project")
        elif filename.startswith("status_"):
            tags.append("status")
        elif filename.startswith("user_"):
            tags.append("user")
        elif filename.startswith("idea_"):
            tags.append("idea")

        content_preview = body[:800] if body else description

        results.append(ConnectorResult(
            source="claude-code",
            source_ref=f"memory_{filename}",
            type="memory",
            title=f"{name}: {description[:100]}" if description else name,
            content=content_preview,
            created_at=created,
            tags=tags,
            metadata={
                "file_path": filepath,
                "frontmatter": {k: v for k, v in fm.items() if isinstance(v, (str, int, float))},
            },
        ))

    return results


def _tags_from_path(file_path: str) -> list[str]:
    tags = []
    path_lower = file_path.lower()
    if "/obsidian" in path_lower or "obsidian life" in path_lower:
        tags.append("obsidian")
    if "/content/" in path_lower or "content" in path_lower:
        tags.append("content")
    if "/relay/" in path_lower or "relay" in path_lower:
        tags.append("relay")
    if "/glaze/" in path_lower:
        tags.append("glaze")
    if "resume" in path_lower or "cv" in path_lower:
        tags.append("resume")
    if "dashboard" in path_lower:
        tags.append("dashboard")
    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".py", ".ts", ".tsx", ".js", ".jsx"):
        tags.append("code")
    elif ext in (".md",):
        tags.append("markdown")
    elif ext in (".html",):
        tags.append("html")
    elif ext in (".json",):
        tags.append("config")
    return tags


def scan(config: dict) -> list[ConnectorResult]:
    results = []
    results.extend(scan_sessions_index(config))
    results.extend(scan_memory(config))
    results.extend(scan_jsonl(config))
    return results
