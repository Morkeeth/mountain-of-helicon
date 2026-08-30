#!/usr/bin/env python3
"""Parse truth-daily-latest.txt → truth-daily-summary.json with delta."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

STORE = Path.home() / ".helicon"
RECEIPT = STORE / "truth-daily-latest.txt"
SUMMARY = STORE / "truth-daily-summary.json"
PREV = STORE / "truth-daily-summary.prev.json"

ROW_RE = re.compile(
    r"^\s+(\d+)\s+(\d+)\s+(\d+[dh]?)\s+(\S.+?)\s*$"
)
SECTION_RE = re.compile(r"^--- (.+?) · (.+?) ---")


def parse_receipt(text: str) -> dict:
    stores: list[dict] = []
    top_files: list[dict] = []
    current_label = "unknown"
    flagged_rows = 0
    files_seen: set[str] = set()

    for line in text.splitlines():
        sec = SECTION_RE.match(line)
        if sec:
            current_label = sec.group(1).strip()
            continue
        m = ROW_RE.match(line)
        if not m:
            continue
        score = int(m.group(2))
        if score < 1:
            continue
        flagged_rows += 1
        fname = m.group(4).strip()
        files_seen.add(fname)
        top_files.append(
            {
                "file": fname,
                "score": score,
                "rank": int(m.group(1)),
                "age": m.group(3),
                "store": current_label,
            }
        )

    # Re-scan section headers for scanned/signaled counts
    parts = re.split(r"^--- (.+?) · (.+?) ---\n", text, flags=re.M)
    if len(parts) > 1:
        for i in range(1, len(parts), 3):
            label = parts[i].strip()
            body = parts[i + 2] if i + 2 < len(parts) else ""
            scanned = signaled = 0
            hdr = re.search(
                r"(\d+) files scanned · (\d+) carry a staleness/rot signal",
                body,
            )
            if hdr:
                scanned, signaled = int(hdr.group(1)), int(hdr.group(2))
            stores.append(
                {"label": label, "scanned": scanned, "signaled": signaled}
            )

    top_files.sort(key=lambda x: (-x["score"], x["file"]))
    return {
        "flagged_rows": flagged_rows,
        "flagged_files": len(files_seen),
        "stores": stores,
        "top_files": top_files[:10],
    }


def main() -> int:
    if not RECEIPT.is_file():
        print(f"missing receipt: {RECEIPT}", file=__import__("sys").stderr)
        return 1

    parsed = parse_receipt(RECEIPT.read_text(encoding="utf-8"))
    prev: dict = {}
    if PREV.is_file():
        try:
            prev = json.loads(PREV.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}
    elif SUMMARY.is_file():
        try:
            prev = json.loads(SUMMARY.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    out = {
        "at": now,
        "flagged_rows": parsed["flagged_rows"],
        "flagged_files": parsed["flagged_files"],
        "delta_rows": parsed["flagged_rows"] - int(prev.get("flagged_rows", 0)),
        "delta_files": parsed["flagged_files"] - int(prev.get("flagged_files", 0)),
        "stores": parsed["stores"],
        "top_files": parsed["top_files"],
        "previous_at": prev.get("at"),
        "receipt": str(RECEIPT),
    }

    STORE.mkdir(parents=True, exist_ok=True)
    if SUMMARY.is_file():
        SUMMARY.replace(PREV)
    SUMMARY.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    delta_s = f"{out['delta_files']:+d} files" if out["delta_files"] else "unchanged"
    print(
        f"truth summary: {out['flagged_files']} flagged files "
        f"({delta_s} vs prior) → {SUMMARY}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
