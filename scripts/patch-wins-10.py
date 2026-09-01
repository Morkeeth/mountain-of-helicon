#!/usr/bin/env python3
"""Patch ruling #281: hackathon wins 9 → 10 per prize-ledger.md (2026-08-16).

Paris Innovation (BriefMCP 2nd) moved into the prize-winning set. Updates the
audit_log ruling, supersedes the old correction cube, inserts the new one, and
recompiles GOLDEN_RULES.
"""
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))

from helicon.config import load_config
from helicon.db import init_db, insert_cube
from helicon.gold import write_gold
from helicon.models import HeliconCube
from helicon.scanner import content_hash, make_id

AUDIT_ID = 281
OLD_CUBE = "gc_a4c2f0ab15a5"
TRUTH = "10"
NOTE = ("prize-ledger.md 2026-08-16: Paris Innovation moved in; "
        "BriefMCP was finalist and came 2nd (was 9)")


def main() -> int:
    config = load_config()
    conn = init_db(config["db_path"])
    row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (AUDIT_ID,)).fetchone()
    if row is None:
        print(f"finding #{AUDIT_ID} not found", file=sys.stderr)
        return 1

    d = json.loads(row["details"])
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    wrong = [v for v in ("4", "9") if v != TRUTH]

    d["dates"] = ["4", "9", TRUTH]
    d["all_dates"] = ["4", "9", TRUTH]
    d["value_a"] = TRUTH
    d["support"] = {**d.get("support", {}), TRUTH: d.get("support", {}).get("9", 12) + 1}
    d["line_a"] = d["line_a"].replace("9 hackathon wins", "10 hackathon wins", 1)
    d["overturned_from"] = "9"
    d["overturn_note"] = NOTE

    conn.execute(
        "UPDATE audit_log SET human_decision = ?, resolved_at = ?, details = ? WHERE id = ?",
        (f"resolved:{TRUTH}", now, json.dumps(d), AUDIT_ID),
    )
    conn.execute(
        "UPDATE helicon_cubes SET review_status = 'superseded', last_reinforced = ? "
        "WHERE id = ?",
        (now, OLD_CUBE),
    )

    content = (
        f"{d['person'].title()}'s {d['topic']} is {TRUTH} "
        f"(human resolution of finding #{AUDIT_ID}, {now[:10]}). "
        f"The competing value(s) {', '.join(wrong)} are wrong; any memory "
        f"asserting them predates this resolution. Note: {NOTE}"
    )
    cube = HeliconCube(
        id=make_id(),
        source="human-resolution",
        source_ref=f"audit:{AUDIT_ID}",
        type="decision",
        title=f"Resolved: {d['person'].title()} {d['topic']} = {TRUTH}",
        content=content,
        summary="",
        content_hash=content_hash(content),
        created_at=now,
        valid_from=now,
        last_reinforced=now,
        confidence=1.0,
        review_status="approved",
    )
    insert_cube(conn, cube)
    conn.commit()

    res = write_gold(conn, config)
    line = next((ln for ln in res["md"].splitlines() if "hackathon wins" in ln), "")
    print(f"patched finding #{AUDIT_ID} → wins = {TRUTH}")
    print(f"correction cube: {cube.id} (superseded {OLD_CUBE})")
    print(f"GOLDEN_RULES: {res['path']}")
    print(f"ruling line: {line.strip()}")
    if f"= {TRUTH}" not in line:
        print("ERROR: GOLDEN_RULES does not show 10 wins", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
