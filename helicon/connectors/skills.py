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
    full = (f"{description}\n\n{body}" if description else body).strip()
    content = full[:SKILL_BODY_MAX]
    # The cap is a storage/token budget, not a claim that this is the whole
    # skill — a real skill runs 3-11k chars, so most of the body is NOT here.
    # Record the cut: the battery reads this content to judge THINNESS and
    # REDUNDANCY, and an unmarked truncation would have it grade an artifact of
    # this line rather than the skill (two skills whose first 2k agree look
    # identical; a fat skill looks thin). Downstream can now tell.
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
            "body_truncated": len(full) > SKILL_BODY_MAX,
            "body_full_len": len(full),
        },
    )


# vendored / build dirs are not your skills library — never audit them
_JUNK = ("/node_modules/", "/.git/", "/dist/", "/build/", "/.venv/", "/site-packages/")

# How much of a skill body is stored. Real skills run 3-11k chars, so this
# cuts most of them; cubes carry body_truncated + body_full_len so nothing
# downstream mistakes the stored text for the whole skill.
SKILL_BODY_MAX = 2000


def _find_skill_files(root: str) -> list[str]:
    root = os.path.expanduser(root)
    found = []
    # canonical SKILL.md anywhere under root
    found += glob(os.path.join(root, "**", "SKILL.md"), recursive=True)
    found += glob(os.path.join(root, "**", "skill.md"), recursive=True)
    # flat skill markdown directly under a skills/ dir (e.g. ~/.claude/skills/*.md)
    if os.path.basename(os.path.normpath(root)) == "skills":
        found += glob(os.path.join(root, "*.md"))
    # Dedupe on file IDENTITY, not on the path string. macOS is case-insensitive,
    # so the SKILL.md and skill.md globs return the SAME file under two
    # spellings; a set() of paths keeps both and every skill gets ingested
    # twice. The redundancy test would then dutifully report a duplicate that
    # this function invented. Case-sensitive filesystems never saw it.
    out, seen = [], set()
    for f in sorted(found):
        if any(j in f for j in _JUNK):
            continue
        try:
            st = os.stat(f)
            key = (st.st_dev, st.st_ino)
        except OSError:
            key = os.path.normcase(os.path.realpath(f))
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


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
