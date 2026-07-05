"""Stackwatch — the rest of the harness, under the same exam.

Memory was never just the database: an agent stack runs on standing context
(CLAUDE.md), skills, ROUTINES (cron/launchd), and the OUTPUT its agents
claim to have produced. Each of those rots in its own way, and each rot
files into the same loop: finding -> evidence -> your ruling.

Three deterministic checks, zero LLM:

  routines  a scheduled job whose log went silent is a dead limb the stack
            still believes in. Crontab entries with a log path are checked
            for log freshness against ~3x their interval.
  outputs   agents claim 'Created: X' all day. A claimed file that does not
            exist on disk is output drift — the fake-done catalogue's most
            checkable entry.
  context   context bloat is a measured tax: 91.6% -> 71% task completion,
            full-history vs pruned (arXiv 2606.10209, verified). Standing
            CLAUDE.md over budget files a finding with its token weight.

All findings are idempotent by a stable key in details, same as pairing.
"""
import json
import os
import re
import sqlite3
import subprocess
from datetime import datetime

from helicon.models import AuditResult
from helicon.db import insert_audit

CONTEXT_BUDGET_TOKENS = 6000
LOG_SILENCE_FACTOR = 3.0


def _cron_interval_minutes(spec: str) -> float | None:
    """Rough interval from the first two cron fields. Good enough to know
    whether a log has been silent for ~3 intervals."""
    parts = spec.split()
    if len(parts) < 2:
        return None
    minute, hour = parts[0], parts[1]
    m = re.match(r"\*/(\d+)$", minute)
    if m:
        return float(m.group(1))
    h = re.match(r"\*/(\d+)$", hour)
    if h:
        return float(h.group(1)) * 60
    if minute.isdigit() and hour == "*":
        return 60.0
    if minute.isdigit() and h is None and hour.isdigit():
        return 24 * 60.0
    return None


def routine_findings() -> list[dict]:
    out = []
    try:
        cron = subprocess.run(["crontab", "-l"], capture_output=True,
                              text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return out
    now = datetime.now().timestamp()
    for line in cron.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        logm = re.search(r">>?\s*(\S+\.log)", line)
        if not logm:
            continue
        interval = _cron_interval_minutes(line)
        if not interval:
            continue
        log_path = os.path.expanduser(logm.group(1))
        # relative log paths resolve against the cron line's cd, if any
        cdm = re.search(r"cd\s+(\S+)", line)
        if not os.path.isabs(log_path) and cdm:
            log_path = os.path.join(os.path.expanduser(cdm.group(1)), log_path)
        name = (re.search(r"#\s*(.+)$", line) or ["", log_path])[1]
        if not os.path.exists(log_path):
            out.append({"key": f"routine|{log_path}|missing",
                        "finding": f"Routine '{name.strip()}' has never written its "
                                   f"log ({log_path}) — scheduled but possibly dead",
                        "severity": "warning", "evidence": line[:160]})
            continue
        silent_min = (now - os.path.getmtime(log_path)) / 60
        if silent_min > interval * LOG_SILENCE_FACTOR:
            out.append({"key": f"routine|{log_path}|silent",
                        "finding": f"Routine '{name.strip()}' silent for "
                                   f"{silent_min/60:.1f}h (runs every "
                                   f"{interval:.0f}min) — the stack still "
                                   f"believes in a dead limb",
                        "severity": "warning", "evidence": line[:160]})
    return out


EPHEMERAL = ("/tmp/", "/scratchpad/", "/T/")


def output_findings(conn: sqlite3.Connection, since_days: int = 2,
                    ephemeral: tuple = EPHEMERAL) -> list[dict]:
    """Claimed-created files that do not exist. The claim is the cube; the
    filesystem is the truth."""
    out = []
    rows = conn.execute(
        "SELECT id, title, content, created_at FROM helicon_cubes "
        "WHERE source = 'claude-code' AND title LIKE 'Created:%' "
        "AND review_status IN ('pending','revised','approved') "
        "AND merged_into IS NULL "
        "AND created_at >= datetime('now', ?)",
        (f"-{since_days} days",),
    ).fetchall()
    for r in rows:
        m = re.search(r"File: (/[^\n]+)", r["content"] or "")
        if not m:
            continue
        path = m.group(1).strip()
        if any(seg in path for seg in ephemeral):
            continue  # ephemeral by design, absence is not drift
        if not os.path.exists(path):
            out.append({"key": f"output|{path}",
                        "finding": f"Memory points at a dead path: "
                                   f"{os.path.basename(path)} was created at "
                                   f"{path}, which no longer exists (moved, "
                                   f"renamed or archived since)",
                        "severity": "warning",
                        "evidence": f"claim cube {r['id']}, "
                                    f"{(r['created_at'] or '')[:16]}",
                        "cube_id": r["id"]})
    return out


def context_findings() -> list[dict]:
    """Standing context weight vs the measured completion tax."""
    out = []
    for path in (os.path.expanduser("~/.claude/CLAUDE.md"), "CLAUDE.md"):
        if not os.path.exists(path):
            continue
        chars = len(open(path, encoding="utf-8", errors="replace").read())
        tokens = chars // 4
        if tokens > CONTEXT_BUDGET_TOKENS:
            out.append({"key": f"context|{path}",
                        "finding": f"Standing context {path} is ~{tokens:,} "
                                   f"tokens (budget {CONTEXT_BUDGET_TOKENS:,}). "
                                   f"Context bloat is measured at 91.6% -> 71% "
                                   f"task completion (full-history vs pruned, "
                                   f"arXiv 2606.10209). Every turn pays this",
                        "severity": "info",
                        "evidence": f"{chars:,} chars; prune or split with "
                                    f"@imports; helicon's superseded-section "
                                    f"findings name the dead weight"})
    return out


def _existing_keys(conn: sqlite3.Connection) -> set:
    keys = set()
    for row in conn.execute(
        "SELECT details FROM audit_log WHERE audit_type IN "
        "('routine', 'output', 'context')"
    ):
        try:
            k = json.loads(row["details"]).get("key")
            if k:
                keys.add(k)
        except (json.JSONDecodeError, TypeError):
            pass
    return keys


def stack_scan(conn: sqlite3.Connection) -> dict:
    """Run all three checks, file new findings idempotently."""
    existing = _existing_keys(conn)
    now = datetime.utcnow().isoformat()
    filed = {"routine": 0, "output": 0, "context": 0}
    for kind, items in (("routine", routine_findings()),
                        ("output", output_findings(conn, ephemeral=EPHEMERAL)),
                        ("context", context_findings())):
        for it in items:
            if it["key"] in existing:
                continue
            insert_audit(conn, AuditResult(
                audit_type=kind, target_type="cube" if it.get("cube_id") else "stack",
                target_id=it.get("cube_id") or it["key"],
                finding=it["finding"], severity=it["severity"],
                proposed_action="review",
                details={"key": it["key"], "evidence": it["evidence"]},
                audited_at=now))
            filed[kind] += 1
    conn.commit()
    return filed
