import fnmatch
import os
import re
from datetime import datetime
from glob import glob

from helicon.models import ConnectorResult


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm = {}
    for line in parts[1].strip().split("\n"):
        line = line.strip()
        if ":" in line and not line.startswith("-") and not line.startswith("#"):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",") if v.strip()]
            fm[key] = val
    body = parts[2].strip()
    return fm, body


def classify_by_path(rel_path: str) -> tuple[str, list[str]]:
    tags = ["obsidian"]
    cube_type = "draft"

    parts = rel_path.split(os.sep)
    if not parts:
        return cube_type, tags

    top = parts[0]

    if top.startswith("00"):
        cube_type = "dashboard"
        tags.append("dashboard")
    elif top.startswith("01"):
        cube_type = "project"
        tags.append("project")
        if len(parts) > 1:
            tags.append(parts[1].lower().replace(" ", "-"))
    elif top.startswith("02"):
        cube_type = "draft"
        tags.append("content")
    elif top.startswith("03"):
        cube_type = "idea"
        tags.append("idea")
    elif top.lower() == "archive":
        cube_type = "archive"
        tags.append("archive")
    elif top.lower() == "human made":
        cube_type = "personal"
        tags.append("personal")

    filename = parts[-1].lower()
    if "resume" in filename or "cv" in filename:
        tags.append("resume")
    if "roadmap" in filename:
        tags.append("roadmap")
    if "strategy" in filename:
        tags.append("strategy")

    return cube_type, tags


PREVIEW_CHARS = 1000  # what a note cube holds; the rest of a long note is not searchable
SECTION_CHARS = 1200  # the size of one section cube of a note read in full


def split_sections(body: str, size: int = SECTION_CHARS) -> list[tuple[str, str]]:
    """Cut a note into (heading, text) pieces of at most `size` characters.

    A heading starts a new piece. A long section is cut at line ends, so a table
    row or a list item is never split in two.
    """
    pieces = []
    heading, lines, used = "", [], 0

    def close():
        nonlocal lines, used
        text = "\n".join(lines).strip()
        if text:
            pieces.append((heading, text))
        lines, used = [], 0

    for line in body.split("\n"):
        match = re.match(r"^#{1,6}\s+(.*)", line)
        if match:
            close()
            heading = match.group(1).strip()
            continue
        if lines and used + len(line) + 1 > size:
            close()
        lines.append(line[:size])
        used += min(len(line), size) + 1
    close()
    return pieces


def scan(config: dict) -> list[ConnectorResult]:
    vault_path = config.get("vault_path", "")
    if not vault_path or not os.path.exists(vault_path):
        return []

    skip_dirs = set(config.get("skip_dirs", [".obsidian", ".trash"]))
    max_depth = config.get("max_depth", 3)
    # A note cube holds the first PREVIEW_CHARS only. A fact deeper in a long note
    # is in no cube, whatever the folder depth. Notes that match one of these
    # vault-relative patterns are also held section by section, in full.
    full_text = [p for p in (config.get("full_text_paths") or []) if isinstance(p, str) and p]

    results = []

    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        rel_root = os.path.relpath(root, vault_path)
        depth = 0 if rel_root == "." else rel_root.count(os.sep) + 1
        if depth > max_depth:
            dirs.clear()
            continue

        for filename in files:
            if not filename.endswith(".md"):
                continue

            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, vault_path)

            try:
                with open(filepath) as f:
                    text = f.read()
            except Exception:
                continue

            if not text.strip():
                continue

            fm, body = parse_frontmatter(text)

            date = fm.get("date", "")
            if not date:
                mtime = os.path.getmtime(filepath)
                date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

            created_at = f"{date}T00:00:00" if len(date) == 10 else date

            fm_tags = fm.get("tags", [])
            if isinstance(fm_tags, str):
                fm_tags = [fm_tags]

            source = fm.get("source", "unknown")
            status = fm.get("status", "")

            cube_type, path_tags = classify_by_path(rel_path)
            all_tags = list(set(path_tags + fm_tags))

            title_base = filename.replace(".md", "").replace("-", " ").replace("_", " ")
            heading = ""
            for line in body.split("\n"):
                if line.startswith("# "):
                    heading = line[2:].strip()
                    break
            title = heading or title_base

            content_preview = body[:PREVIEW_CHARS]

            results.append(ConnectorResult(
                source="obsidian",
                source_ref=rel_path,
                type=cube_type,
                title=title,
                content=content_preview,
                created_at=created_at,
                tags=all_tags,
                metadata={
                    "file_path": filepath,
                    "vault_relative": rel_path,
                    "frontmatter_source": source,
                    "status": status,
                },
            ))

            posix_path = rel_path.replace(os.sep, "/")
            if len(body) > PREVIEW_CHARS and any(fnmatch.fnmatch(posix_path, p) for p in full_text):
                for number, (heading, text) in enumerate(split_sections(body), 1):
                    results.append(ConnectorResult(
                        source="obsidian",
                        source_ref=f"{rel_path}#section-{number}",
                        type=cube_type,
                        title=f"{title}: {heading}" if heading and heading != title else f"{title} (part {number})",
                        content=text,
                        created_at=created_at,
                        tags=list(set(all_tags + ["full-text"])),
                        metadata={
                            "file_path": filepath,
                            "vault_relative": rel_path,
                            "frontmatter_source": source,
                            "status": status,
                            "section": number,
                            "heading": heading,
                        },
                    ))

    return results
