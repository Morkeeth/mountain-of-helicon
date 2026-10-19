"""Measured learnings connector: a short curated list of results, each with its source.

A measured result ("the full setup carries 40,000 tokens before the first word") is
worth more than a note about it, and it is easy to lose: it sits deep in a report, in
a table, past the part of the file a note cube holds. This connector reads a small
JSON Lines file the operator curates. One line is one result:

    {"id": "SETUP-COST", "claim": "...", "number": "...", "when": "2026-10-10",
     "n": "5 trials", "source": "/path/to/the/file/that/proves/it",
     "check": ["40,503"], "caveat": "..."}

A line with no `source` is skipped: a number with no source is not a learning. On
every scan the source file is opened and each `check` string is looked for in it. The
cube says whether the source still holds the number, so a result whose proof moved or
changed does not keep its standing.

Opt-in: nothing is read unless the connector config holds `files`.
"""
import json
import os
from datetime import datetime

from helicon.models import ConnectorResult


def _probe(source: str, checks: list[str]) -> tuple[str, list[str]]:
    """Open the source and look for each check string. Returns (state, missing)."""
    path = os.path.expanduser(source)
    if not os.path.isfile(path):
        return "source file not found", list(checks)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return "source file not readable", list(checks)
    missing = [c for c in checks if c not in text]
    if missing:
        return "source no longer holds the number", missing
    return ("source holds the number" if checks else "source file is there, no number checked"), []


def scan(config: dict) -> list[ConnectorResult]:
    results = []
    seen = set()
    today = datetime.now().strftime("%Y-%m-%d")
    for listed in config.get("files") or []:
        path = os.path.abspath(os.path.expanduser(str(listed)))
        if path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict) or not row.get("claim") or not row.get("source"):
                    continue
                checks = [str(c) for c in row.get("check") or [] if str(c)]
                state, missing = _probe(str(row["source"]), checks)
                verified = state == "source holds the number"
                ident = str(row.get("id") or row["claim"][:40])
                when = str(row.get("when") or "")
                lines = [
                    f"Measured: {row['claim']}",
                    f"Source: {row['source']}",
                    f"Source check: {state}" + (f" (missing: {', '.join(missing)})" if missing else ""),
                    f"Number: {row.get('number', '')}",
                    f"When: {when}. Population: {row.get('n', 'not stated')}",
                ]
                if row.get("caveat"):
                    lines.append(f"Caveat: {row['caveat']}")
                title = f"Measured: {row['claim']}"
                if not verified:
                    title = f"UNVERIFIED measurement: {row['claim']}"
                results.append(ConnectorResult(
                    source="learnings",
                    source_ref=f"{os.path.basename(path)}#{ident}",
                    type="learning",
                    title=title[:240],
                    content="\n".join(lines),
                    created_at=f"{when}T00:00:00" if len(when) == 10 else when,
                    tags=["learning", "measured", "source-verified" if verified else "source-unverified"],
                    metadata={"id": ident, "number": str(row.get("number", "")), "source_path": str(row["source"]),
                              "source_state": state, "source_verified": verified, "checked_on": today,
                              "missing_in_source": missing, "file_path": path},
                ))
    return results
