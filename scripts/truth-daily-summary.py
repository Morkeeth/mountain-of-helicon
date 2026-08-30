#!/usr/bin/env python3
"""Daily truth cross-check → machine-readable G6 summary (no text parsing)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from helicon.truth import format_report, scan_store

STORE = Path.home() / ".helicon"
SUMMARY = STORE / "truth-daily-summary.json"
PREV = STORE / "truth-daily-summary.prev.json"
RECEIPT = STORE / "truth-daily-latest.txt"

VAULT = Path(
    os.environ.get(
        "OBSIDIAN_VAULT",
        Path.home()
        / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian LIFE",
    )
)
STORES: list[tuple[str, Path]] = [
    ("SLASK", VAULT / "! ❄SLASK 🧊"),
    (
        "dashboard",
        VAULT / "00 Dashboard",
    ),
    (
        "claude-memory",
        Path(
            os.environ.get(
                "CLAUDE_MEMORY",
                Path.home() / ".claude/projects/-Users-morkeeth/memory",
            )
        ),
    ),
]


def _load_prev() -> dict:
    for path in (PREV, SUMMARY):
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
    return {}


def _g6_flagged(prev: dict, out: dict) -> int:
    g6 = prev.get("g6") or {}
    return int(g6.get("flagged", prev.get("flagged_files", 0)))


def main() -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    prev = _load_prev()
    prev_flagged = _g6_flagged(prev, prev)

    store_rows: list[dict] = []
    flagged_items: list[dict] = []
    human: list[str] = [
        f"=== helicon truth daily · {now.astimezone().isoformat(timespec='seconds')} ==="
    ]

    for label, path in STORES:
        human.append("")
        human.append(f"--- {label} · {path} ---")
        if not path.exists():
            human.append(f"[skip] path missing: {path}")
            store_rows.append(
                {"label": label, "path": str(path), "scanned": 0, "flagged": 0, "skip": True}
            )
            continue

        res = scan_store(str(path))
        if res.get("error"):
            human.append(f"[warn] {res['error']}")
            store_rows.append(
                {
                    "label": label,
                    "path": str(path),
                    "scanned": 0,
                    "flagged": 0,
                    "error": res["error"],
                }
            )
            continue

        store_rows.append(
            {
                "label": label,
                "path": str(path),
                "scanned": res["total"],
                "flagged": res["flagged"],
                "clean": res.get("clean", 0),
            }
        )
        human.append(format_report(res))
        for it in res["items"]:
            if it["score"] < 1:
                continue
            flagged_items.append(
                {
                    "file": it["file"],
                    "path": it["path"],
                    "score": it["score"],
                    "age_days": it["age_days"],
                    "store": label,
                }
            )

    human.append("")
    human.append(f"=== end {now.astimezone().isoformat(timespec='seconds')} ===")

    flagged_items.sort(key=lambda x: (-x["score"], x["file"]))
    flagged = len(flagged_items)
    delta = flagged - prev_flagged
    top_item = flagged_items[0] if flagged_items else None

    out = {
        "at": now.isoformat(),
        "g6": {
            "flagged": flagged,
            "delta": delta,
            "top": (
                {
                    "file": top_item["file"],
                    "score": top_item["score"],
                    "store": top_item["store"],
                }
                if top_item
                else None
            ),
        },
        "stores": store_rows,
        "top": flagged_items[:10],
        "previous_at": prev.get("at"),
    }

    STORE.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text("\n".join(human) + "\n", encoding="utf-8")
    if SUMMARY.is_file():
        SUMMARY.replace(PREV)
    SUMMARY.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    delta_s = f"{delta:+d} vs prior" if prev.get("at") else "first reading"
    top_name = top_item["file"] if top_item else "—"
    print(
        f"truth summary: {flagged} flagged ({delta_s}) · top {top_name} → {SUMMARY}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
