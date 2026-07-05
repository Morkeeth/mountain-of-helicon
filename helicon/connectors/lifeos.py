"""Life-OS connector — the operator's own second brain as first-class cubes.

Reads a LIST of markdown roots (Obsidian vault folders, a Claude Code memory
dir — any directory of .md files a human actually lives out of) strictly
READ-ONLY, and splits every file into SECTION-level cubes (agent_rules
granularity) so a single drifting claim inside a living doc is catchable by
the same checks that watch agent memory.

Two rules learned from the Jul 5 manual vault audit:
  - frontmatter `date:` beats file mtime: stamping a correction banner on a
    June doc must not make the doc look born today, or every staleness
    check goes blind the moment a human touches the file.
  - `strip_pattern` drops matching lines before ingest. The rot benchmark
    uses it to remove the human audit's `> **LOUPE` banners — they are the
    answer key, and the answer key must never leak into the input. Watch
    mode leaves it unset and ingests everything.

Opt-in: no `roots` in config -> returns [] silently (adapter pattern).
"""
import os
import re
from datetime import datetime

from helicon.models import ConnectorResult
from helicon.connectors.agent_rules import _slug, _split_sections
from helicon.connectors.obsidian import classify_by_path, parse_frontmatter

DEFAULT_SKIP_DIRS = {".obsidian", ".trash", ".git"}


def scan(config: dict) -> list[ConnectorResult]:
    roots = config.get("roots", [])
    if not roots:
        return []

    skip_dirs = set(config.get("skip_dirs", DEFAULT_SKIP_DIRS))
    strip_rx = (re.compile(config["strip_pattern"], re.MULTILINE)
                if config.get("strip_pattern") else None)

    results = []
    for root in roots:
        root = os.path.expanduser(root)
        if not os.path.isdir(root):
            continue
        label = os.path.basename(os.path.normpath(root))

        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for filename in sorted(files):
                if not filename.endswith(".md"):
                    continue
                filepath = os.path.join(dirpath, filename)
                rel = os.path.join(label, os.path.relpath(filepath, root))
                try:
                    with open(filepath, encoding="utf-8") as f:
                        text = f.read()
                except OSError:
                    continue
                if strip_rx is not None:
                    text = "\n".join(ln for ln in text.splitlines()
                                     if not strip_rx.match(ln))
                if not text.strip():
                    continue

                fm, body = parse_frontmatter(text)
                date = str(fm.get("date", "") or "")
                if not date:
                    date = datetime.fromtimestamp(
                        os.path.getmtime(filepath)).strftime("%Y-%m-%d")
                created_at = f"{date}T00:00:00" if len(date) == 10 else date

                cube_type, tags = classify_by_path(rel)
                fm_tags = fm.get("tags", [])
                if isinstance(fm_tags, str):
                    fm_tags = [fm_tags]

                for heading, section in _split_sections(body):
                    results.append(ConnectorResult(
                        source="lifeos",
                        source_ref=f"{rel}#{_slug(heading)}",
                        type=cube_type,
                        title=f"[{os.path.splitext(filename)[0]}] {heading}",
                        content=section,
                        created_at=created_at,
                        tags=["lifeos", *tags, *fm_tags],
                        metadata={"file": rel, "heading": heading,
                                  "status": str(fm.get("status", "") or "")},
                    ))
    return results
