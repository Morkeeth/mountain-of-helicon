"""Skills connector — audit an agent's SKILL library as memory.

Agent Skills (SKILL.md, an open standard since Dec 2025) are the newest durable
agent-memory surface: folders of instructions an agent loads on demand. They
proliferate fast and rot exactly like CLAUDE.md — stale skills, near-duplicate
triggers that fight each other, thin descriptions that never fire, skills that
contradict a rule elsewhere. Nobody audits a skills library. Helicon does: each
skill becomes a cube, so the battery (redundancy/thinness/contradiction) and
snapshot-regression apply to skills too.

Handles both shapes:
  - standard SKILL.md with YAML frontmatter (name, description) + body
  - plain skill markdown (e.g. Helicon's own helicon-*.md write-backs): first
    heading is the name, body is the content.
"""
import os
import re
from datetime import datetime
from glob import glob

from helicon.models import ConnectorResult


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Minimal YAML: flat key: value pairs."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_block = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    fm = {}
    for line in fm_block.splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            fm[m.group(1).strip().lower()] = m.group(2).strip()
    return fm, body


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        m = re.match(r"^#{1,3}\s+(.*)", line)
        if m:
            return m.group(1).strip()
    return ""


def _scan_skill_file(path: str, root: str) -> ConnectorResult | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return None
    if not text.strip():
        return None

    fm, body = _parse_frontmatter(text)
    name = fm.get("name") or _first_heading(body) or os.path.splitext(os.path.basename(path))[0]
    description = fm.get("description", "")
    # A skill's identity for retrieval is its trigger (name + description); the
    # body is the payload. Store both, description first so it drives matching.
    content = (f"{description}\n\n{body}" if description else body).strip()[:2000]
    rel = os.path.relpath(path, root)

    return ConnectorResult(
        source="skills",
        source_ref=f"skills/{rel}",
        type="agent_skill",
        title=f"[skill] {name}",
        content=content,
        created_at=datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
        tags=["skills", "agent-skill"],
        metadata={
            "skill_name": name,
            "description": description,
            "has_frontmatter": bool(fm),
            "path": rel,
            "desc_len": len(description),
        },
    )


# vendored / build dirs are not your skills library — never audit them
_JUNK = ("/node_modules/", "/.git/", "/dist/", "/build/", "/.venv/", "/site-packages/")


def _find_skill_files(root: str) -> list[str]:
    root = os.path.expanduser(root)
    found = []
    # canonical SKILL.md anywhere under root
    found += glob(os.path.join(root, "**", "SKILL.md"), recursive=True)
    found += glob(os.path.join(root, "**", "skill.md"), recursive=True)
    # flat skill markdown directly under a skills/ dir (e.g. ~/.claude/skills/*.md)
    if os.path.basename(os.path.normpath(root)) == "skills":
        found += glob(os.path.join(root, "*.md"))
    return sorted(f for f in set(found) if not any(j in f for j in _JUNK))


def scan(config: dict) -> list[ConnectorResult]:
    roots = config.get("skill_roots") or config.get("roots") or []
    results = []
    seen = set()
    for root in roots:
        rp = os.path.expanduser(root)
        if not os.path.exists(rp):
            continue
        for path in _find_skill_files(rp):
            if path in seen:
                continue
            seen.add(path)
            r = _scan_skill_file(path, rp)
            if r:
                results.append(r)
    return results
