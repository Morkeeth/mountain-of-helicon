"""Letta MemFS connector — a Letta Code "Context Repository" as memory cubes.

Letta Code persists agent memory as a git repo of markdown files ("MemFS"):
each file has YAML frontmatter (a `description` field the agent reads to
decide when to open the file) and a `system/` dir holding the always-loaded
core blocks. This connector treats that repo as a first-class memory store:

  - every *.md file is walked (including system/)
  - each file is split into SECTIONS (same granularity as agent_rules), so
    a single memory block drifting or being dropped is catchable by the
    snapshot-regression core
  - frontmatter `description` rides along in metadata
  - created_at comes from `git log -1 --format=%cI -- <file>` when the dir
    is a git repo (MemFS is versioned, so commit time is the honest write
    time), falling back to file mtime otherwise

Opt-in: no `memfs_dir` in config -> return [] silently.
"""
import os
import subprocess
from datetime import datetime

from helicon.models import ConnectorResult
from helicon.connectors.agent_rules import _slug, _split_sections
from helicon.connectors.obsidian import parse_frontmatter


def _is_git_repo(path: str) -> bool:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path, capture_output=True, text=True, timeout=10,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"
    except Exception:
        return False


def _git_commit_time(repo_dir: str, rel_path: str) -> str:
    """Last commit time (ISO 8601) for a file, or "" if unknown/uncommitted."""
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", rel_path],
            cwd=repo_dir, capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return ""


def scan(config: dict) -> list[ConnectorResult]:
    memfs_dir = os.path.expanduser(config.get("memfs_dir", ""))
    if not memfs_dir:
        return []
    if not os.path.isdir(memfs_dir):
        print(f"  [!] letta-memfs: memfs_dir not found: {memfs_dir}")
        return []

    repo_name = os.path.basename(os.path.normpath(memfs_dir))
    use_git = _is_git_repo(memfs_dir)

    results = []
    for root, dirs, files in os.walk(memfs_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]

        for filename in sorted(files):
            if not filename.endswith(".md"):
                continue

            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, memfs_dir)

            try:
                with open(filepath, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except Exception:
                continue
            if not text.strip():
                continue

            fm, body = parse_frontmatter(text)
            description = fm.get("description", "")
            if not body.strip():
                continue

            created = _git_commit_time(memfs_dir, rel_path) if use_git else ""
            created_from = "git" if created else "mtime"
            if not created:
                created = datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()

            is_system = rel_path.split(os.sep)[0] == "system"
            tags = ["letta-memfs", repo_name.lower()]
            if is_system:
                tags.append("system")

            for heading, section in _split_sections(body):
                results.append(ConnectorResult(
                    source="letta-memfs",
                    source_ref=f"{repo_name}/{rel_path}#{_slug(heading)}",
                    type="letta_memory",
                    title=f"[{repo_name}] {filename} — {heading}",
                    content=section[:2000],
                    created_at=created,
                    tags=list(tags),
                    metadata={
                        "repo": repo_name,
                        "file": rel_path,
                        "heading": heading,
                        "description": description,
                        "is_system": is_system,
                        "created_from": created_from,
                    },
                ))

    return results
