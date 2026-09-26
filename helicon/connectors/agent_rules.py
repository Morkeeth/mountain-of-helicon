"""Agent-rules connector — coding-agent memory as first-class objects.

This is the repositioning core: instead of treating Claude Code / Cursor
*transcripts* as memory, this reads the durable rules files a coding agent
is told to obey every session:

  - CLAUDE.md                        (Claude Code)
  - AGENTS.md / AGENT.md             (Codex, Amp, and others)
  - GEMINI.md                        (Gemini CLI)
  - .cursorrules                     (Cursor, legacy)
  - .cursor/rules/*.mdc              (Cursor, current)
  - .clinerules  (file or dir)       (Cline)
  - .windsurfrules                   (Windsurf)
  - .github/copilot-instructions.md  (GitHub Copilot)

Each file is split into SECTIONS (by markdown heading, else by paragraph
block) so every rule becomes its own retrievable cube. Section granularity
is deliberate: the snapshot-regression core can then catch a *single* rule
being dropped, reordered, or drifting — the "teach once, know when it rots"
loop. A whole-file cube would hide that.

Zero personal data: this reads a repo's own committed agent config, so a
demo can run on any public repo and be reproduced by judges.
"""
import os
import re
from glob import glob
from datetime import datetime

from helicon.models import ConnectorResult

# filename -> which agent it configures (for tags / readable titles)
KNOWN_RULE_FILES = {
    "CLAUDE.md": "claude-code",
    "AGENTS.md": "codex",
    "AGENT.md": "codex",
    "GEMINI.md": "gemini",
    ".cursorrules": "cursor",
    ".clinerules": "cline",
    ".windsurfrules": "windsurf",
}
# nested paths (relative to repo root) that are also agent config
KNOWN_RULE_PATHS = {
    ".github/copilot-instructions.md": "copilot",
}


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "section"


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Return [(heading, body), ...]. Markdown headings win; else paragraph blocks."""
    lines = text.splitlines()
    has_headings = any(re.match(r"^#{1,6}\s+\S", ln) for ln in lines)

    if has_headings:
        sections = []
        heading = "(preamble)"
        buf = []
        for ln in lines:
            m = re.match(r"^#{1,6}\s+(.*)", ln)
            if m:
                if buf and "".join(buf).strip():
                    sections.append((heading, "\n".join(buf).strip()))
                heading = m.group(1).strip()
                buf = []
            else:
                buf.append(ln)
        if buf and "".join(buf).strip():
            sections.append((heading, "\n".join(buf).strip()))
        return [(h, b) for h, b in sections if b]

    # No headings (e.g. a plain .cursorrules): split on blank-line blocks.
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if len(blocks) <= 1:
        body = text.strip()
        return [("(rules)", body)] if body else []
    out = []
    for b in blocks:
        first = b.splitlines()[0].strip()
        heading = (first[:60] + "…") if len(first) > 60 else first
        out.append((heading, b))
    return out


def _scan_file(repo_name: str, repo_path: str, rel_path: str, agent: str) -> list[ConnectorResult]:
    from helicon.pointers import read_contained, refusal_for
    rel_path = rel_path.replace(os.sep, "/")
    if refusal_for(repo_path, rel_path):
        return []
    text = read_contained(repo_path, rel_path)
    if not text or not text.strip():
        return []
    full = os.path.join(repo_path, rel_path)
    try:
        created = datetime.fromtimestamp(os.path.getmtime(full)).isoformat()
    except OSError:
        created = datetime.now().isoformat()
    filename = os.path.basename(rel_path)
    results = []
    for heading, body in _split_sections(text):
        results.append(ConnectorResult(
            source="agent-rules",
            source_ref=f"{repo_name}/{rel_path}#{_slug(heading)}",
            type="agent_rule",
            title=f"[{repo_name}] {filename} — {heading}",
            content=body[:2000],
            created_at=created,
            tags=["agent-rules", agent, repo_name.lower()],
            metadata={
                "repo": repo_name,
                "file": rel_path,
                "agent": agent,
                "heading": heading,
            },
        ))
    return results


def _scan_repo(repo_path: str) -> list[ConnectorResult]:
    from helicon.doorway import _seed_docs
    from helicon.pointers import refusal_for

    repo_name = os.path.basename(os.path.normpath(repo_path))
    results = []

    for rel in _seed_docs(repo_path):
        if refusal_for(repo_path, rel):
            continue
        agent = KNOWN_RULE_FILES.get(rel) or KNOWN_RULE_PATHS.get(rel) or "cursor"
        if rel == "CLAUDE.local.md":
            agent = "claude-code"
        results.extend(_scan_file(repo_name, repo_path, rel, agent))

    # Cline can be a directory of rule files. A symlink that leaves the repo
    # is not listed. _seed_docs already handled a .clinerules file.
    clinerules_dir = os.path.join(repo_path, ".clinerules")
    if (
        os.path.isdir(clinerules_dir)
        and not os.path.islink(clinerules_dir)
        and not refusal_for(repo_path, ".clinerules")
    ):
        for rf in glob(os.path.join(clinerules_dir, "*")):
            rel = os.path.relpath(rf, repo_path).replace(os.sep, "/")
            if refusal_for(repo_path, rel):
                continue
            if os.path.isfile(rf):
                results.extend(_scan_file(repo_name, repo_path, rel, "cline"))

    return results


def scan(config: dict) -> list[ConnectorResult]:
    results = []
    max_repos = config.get("max_repos", 50)

    # Explicit list of repos wins.
    repos = config.get("repos", [])
    seen = set()
    for r in repos:
        p = os.path.expanduser(r)
        if os.path.isdir(p) and p not in seen:
            seen.add(p)
            results.extend(_scan_repo(p))

    # Otherwise (or additionally) scan one level under repos_dir.
    repos_dir = os.path.expanduser(config.get("repos_dir", ""))
    if repos_dir and os.path.isdir(repos_dir):
        count = 0
        for entry in sorted(os.scandir(repos_dir), key=lambda e: e.name):
            if count >= max_repos:
                break
            if not entry.is_dir() or entry.path in seen:
                continue
            repo_results = _scan_repo(entry.path)
            if repo_results:
                seen.add(entry.path)
                results.extend(repo_results)
                count += 1

    return results
