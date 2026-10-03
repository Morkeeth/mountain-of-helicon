"""Explicit selected-memory inspection; read-only SQLite, no remote judge.

Stored text is data, never an instruction. The source document is not reread;
provenance identifies the exact stored revision observed in one transaction.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from .calendar_check import check_weekday_item
from .jev_prechecks import precheck

SCHEMA = "helicon.judge-preview/1"


def _hash(text):
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def _connect(db):
    path = Path(db).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("Choose an existing SQLite store file")
    # as_uri percent-escapes ?, #, %, spaces and non-ASCII path characters.
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("BEGIN")
    return conn


def _item(conn, item_id):
    row = conn.execute("SELECT id, title, content, source, source_ref, created_at, valid_from, "
                       "review_status, merged_into FROM helicon_cubes WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise ValueError("Selected memory ID was not found")
    d = dict(row)
    if not isinstance(d["content"], str) or len(d["content"].encode("utf8")) > 200000:
        raise ValueError("Selected memory must contain at most 200 KB of text")
    d["content_sha256"] = _hash(d["content"])
    d["source_status"] = "Stored snapshot only; original source freshness is unchecked."
    return d


def preview(db, item_id, against=None):
    if not item_id or (against is not None and against == item_id):
        raise ValueError("Choose one memory, or two different memory IDs")
    conn = _connect(db)
    try:
        items = [_item(conn, item_id)]
        if against is not None:
            items.append(_item(conn, against))
    finally:
        conn.close()
    at = datetime.now(timezone.utc).isoformat()
    checks = []
    for item in items:
        result = check_weekday_item(item["content"])
        checks.append({"scope": "single-item", "item_ids": [item["id"]],
                       "rule": "weekday-full-date", "verdict": result["verdict"] if result else "unknown",
                       "detail": result["detail"] if result else "No supported unambiguous weekday/full-date declaration.",
                       "limit": "Calendar-field agreement is not proof the event or whole memory is true."})
    pair = None
    if len(items) == 2:
        result = precheck(items[0]["content"], items[1]["content"])
        pair = {"scope": "pair", "item_ids": [i["id"] for i in items],
                "rule": result["rule"] if result else None,
                "verdict": "contradicted" if result and result["verdict"] == "contradiction" else "unknown",
                "relation": result.get("arithmetic_relation", result["verdict"]) if result else "unexamined",
                "detail": result["reason"] if result else "No supported pair rule applies.",
                "limit": "One matching relation cannot prove two memories consistent. Jev and escalation were not run."}
        checks.append(pair)
    contradicted = any(c["verdict"] == "contradicted" for c in checks)
    modules = {name: hashlib.sha256(Path(__file__).with_name(name + ".py").read_bytes()).hexdigest()
               for name in ("judge_preview", "jev_prechecks", "calendar_check")}
    return {"schema": SCHEMA, "observed_at": at, "read_only": True, "requests": 0, "sql_mutations": 0,
            "storage_limit": "SQLite may create or use sidecar files for locking; no SQL/data mutations are performed.",
            "items": items, "checks": checks, "verdict": "contradicted" if contradicted else "unknown",
            "checker": {"name": "local bounded rules", "module_sha256": modules},
            "jev": {"status": "not_run", "probability": None},
            "escalation": {"status": "not_run"},
            "limit": "Local checks of selected stored text only. No current truth, model verdict or memory change is claimed."}


def print_preview(report):
    print("SELECTED MEMORY · LOCAL CHECK · NO SQL CHANGES OR REQUESTS")
    for item in report["items"]:
        print(f"\n{item['id']} · {item['title']}\n{item['content']}")
        print(f"Stored source: {item['source_ref']}\nContent SHA256: {item['content_sha256']}")
        print(f"Recorded: {item['created_at']} · valid from: {item['valid_from']}")
    print(f"\nObserved: {report['observed_at']}\nOverall: {report['verdict']}")
    for check in report["checks"]:
        print(f"{check['scope']} · {check['rule'] or 'no applicable rule'} · {check['verdict']}: {check['detail']}")
        print(check["limit"])
    print(report["limit"])
    print(report["storage_limit"])
