"""Skills write-back — close the loop the integrity audit opens.

The skills audit (/api/integrity/skills) flags SKILL.md files whose frontmatter
has a missing or empty `description:` — a thin trigger means the skill never
fires. This module fixes them: for each such file, Qwen writes a one-line
description from the skill's body and it is inserted into the frontmatter.

Safety model:
  - dry-run by default: propose, never write
  - --apply writes a `.bak` of the original next to each file BEFORE modifying
  - files that already have a non-empty description are never touched, so a
    second run is a no-op
  - no Qwen key -> skip with a message, never write
"""
import os
import re

from glaze.connectors.skills import _find_skill_files, _parse_frontmatter
from glaze.qwen import complete

# The user-owned root the integrity audit scans (see glaze/api/integrity.py
# _SKILL_ROOTS). The audit also reads the plugin marketplace root, but that is
# vendored third-party content — we never write descriptions back into it.
DEFAULT_SKILLS_DIR = "~/.claude/skills"

_EMPTY_DESC_LINE = re.compile(r"^description:\s*$")


def generate_description(client, body: str, model: str = "qwen3.6-flash") -> str:
    """One-line `description:` value for a skill, written by Qwen from the body.
    Returns "" when the client is missing or the call yields nothing usable."""
    if client is None or not body.strip():
        return ""
    raw = complete(
        client,
        "You write the `description:` frontmatter line for agent SKILL.md files. "
        "Given a skill body, reply with exactly ONE line describing when the skill "
        "should trigger and what it does. Under 140 characters. Plain text only: "
        "no quotes, no markdown, no 'description:' prefix.",
        body[:2000],
        model,
        operation="skill_description",
    )
    if not raw:
        return ""
    line = raw.strip().splitlines()[0].strip().strip("\"'`").strip()
    if line.lower().startswith("description:"):
        line = line.split(":", 1)[1].strip()
    return line[:200]


def insert_description(text: str, description: str) -> str:
    """Return `text` with `description:` set in the YAML frontmatter.

    - frontmatter with an empty `description:` line -> the line is filled in
    - frontmatter without the key -> the line is appended inside the block
    - no frontmatter at all -> a minimal block is prepended, body untouched
    """
    line = f"description: {description}"
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            head_lines = text[:end].split("\n")
            for i, hl in enumerate(head_lines):
                if _EMPTY_DESC_LINE.match(hl):
                    head_lines[i] = line
                    return "\n".join(head_lines) + text[end:]
            head_lines.append(line)
            return "\n".join(head_lines) + text[end:]
    return f"---\n{line}\n---\n\n{text}"


def fix_skills(skills_dir: str, client=None, model: str = "qwen3.6-flash",
               apply: bool = False) -> dict:
    """Find SKILL.md files under `skills_dir` lacking a non-empty description
    and (propose | write) one for each. Returns per-file records:

      action: has_description | proposed | fixed | skipped_no_client | failed

    Writes happen only with apply=True, and each modified file first gets a
    `<name>.bak` copy of its original bytes next to it.
    """
    root = os.path.expanduser(skills_dir)
    records = []
    for path in _find_skill_files(root):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        rel = os.path.relpath(path, root)
        fm, body = _parse_frontmatter(text)

        if fm.get("description", "").strip():
            records.append({"path": path, "rel": rel, "action": "has_description"})
            continue

        if client is None:
            records.append({"path": path, "rel": rel, "action": "skipped_no_client"})
            continue

        description = generate_description(client, body or text, model)
        if not description:
            records.append({"path": path, "rel": rel, "action": "failed"})
            continue

        if apply:
            with open(path + ".bak", "w", encoding="utf-8") as f:
                f.write(text)
            with open(path, "w", encoding="utf-8") as f:
                f.write(insert_description(text, description))
            action = "fixed"
        else:
            action = "proposed"
        records.append({"path": path, "rel": rel, "action": action,
                        "description": description})

    counts = {}
    for r in records:
        counts[r["action"]] = counts.get(r["action"], 0) + 1
    return {"skills_dir": root, "apply": apply, "records": records, "counts": counts}
