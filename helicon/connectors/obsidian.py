import fnmatch
import logging
import os
import re
import stat
import threading
from datetime import datetime
from glob import glob

from helicon.models import ConnectorResult

log = logging.getLogger(__name__)

READ_TIMEOUT = 5.0  # seconds one note may take to read; config key `read_timeout`
_SF_DATALESS = 0x40000000  # macOS: the file's bytes are not on this disk


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


def read_note(path: str, timeout: float = READ_TIMEOUT) -> tuple[str | None, str]:
    """(text, "") for a note that is on this disk, or (None, why it was skipped).

    A vault in iCloud holds notes that are not on the disk: the name is there, the
    bytes are not. Opening one makes the system fetch it, and with no network or a
    stuck sync that open never returns, so one such note hung the whole scan. Three
    guards, cheapest first: a file the system marks as not downloaded is not opened;
    anything that is not a regular file is not opened; every other read runs in a
    worker with a time limit. A note that fails to decode or to open is dropped
    without a reason, as before.
    """
    try:
        info = os.stat(path)
    except OSError:
        return None, ""
    if getattr(info, "st_flags", 0) & _SF_DATALESS:
        return None, "not downloaded from iCloud (dataless file)"
    if not stat.S_ISREG(info.st_mode):
        return None, "not a regular file"

    box = {}

    def work():
        try:
            box["text"] = _read_file(path)
        except Exception:
            box["text"] = None

    worker = threading.Thread(target=work, name="helicon-vault-read", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        return None, f"the read did not finish in {timeout:g} s"
    return box.get("text"), ""


def _read_file(path: str) -> str:
    with open(path) as handle:
        return handle.read()


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

    try:
        read_timeout = float(config.get("read_timeout", READ_TIMEOUT))
    except (TypeError, ValueError):
        read_timeout = READ_TIMEOUT

    results = []
    skipped = []

    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        rel_root = os.path.relpath(root, vault_path)
        depth = 0 if rel_root == "." else rel_root.count(os.sep) + 1
        if depth > max_depth:
            dirs.clear()
            continue

        for filename in files:
            if filename.startswith(".") and filename.endswith(".md.icloud"):
                # The sidecar iCloud leaves in place of a note it has evicted.
                rel_path = os.path.relpath(os.path.join(root, filename), vault_path)
                skipped.append(rel_path)
                log.warning("obsidian: skipped %s: iCloud placeholder, the note is not on this disk", rel_path)
                continue
            if not filename.endswith(".md"):
                continue

            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, vault_path)

            text, why = read_note(filepath, read_timeout)
            if why:
                skipped.append(rel_path)
                log.warning("obsidian: skipped %s: %s", rel_path, why)
                continue
            if text is None:
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

    if skipped:
        log.warning("obsidian: %d note(s) skipped because they could not be read from this disk. "
                    "Download them in Finder and scan again.", len(skipped))
    return results
