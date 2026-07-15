"""Stackwatch — the rest of the harness, under the same exam.

Memory was never just the database: an agent stack runs on standing context
(CLAUDE.md), skills, ROUTINES (cron/launchd), and the OUTPUT its agents
claim to have produced. Each of those rots in its own way, and each rot
files into the same loop: finding -> evidence -> your ruling.

Five deterministic checks, zero LLM:

  routines  a scheduled job whose log went silent is a dead limb the stack
            still believes in. Crontab AND LaunchAgent entries with a log path
            are checked for freshness against their own cadence (a frequent job
            gets 3x slack; for a daily job, one missed run IS the failure).
  mcp       an MCP server that is registered but cannot speak is a dead limb
            too: every tool it serves goes silently missing from every session.
            Probed with the real protocol, because a process that starts is not
            a server that speaks.
  nightly   the stack's own consolidation, asserted from the run record it
            writes about itself — a STATE `helicon doctor` prints every time you
            look, healthy or not, because the Jul 15 skip hid in the absence of
            an alarm.
  outputs   agents claim 'Created: X' all day. A claimed file that does not
            exist on disk is output drift — the fake-done catalogue's most
            checkable entry.
  context   context bloat is a measured tax: 91.6% -> 71% task completion,
            full-history vs pruned (arXiv 2606.10209, verified). Standing
            CLAUDE.md over budget files a finding with its token weight.

All findings are idempotent by a stable key in details, same as pairing.
"""
import glob
import json
import os
import plistlib
import re
import sqlite3
import subprocess
from datetime import datetime, timezone

from helicon.models import AuditResult
from helicon.db import insert_audit

CONTEXT_BUDGET_TOKENS = 6000
LOG_SILENCE_FACTOR = 3.0
DAILY_GRACE_MINUTES = 6 * 60


def _cron_interval_minutes(spec: str) -> float | None:
    """Rough interval from the first two cron fields. Good enough to know
    whether a log has been silent for ~3 intervals."""
    parts = spec.split()
    if len(parts) < 5:
        return None
    minute, hour = parts[0], parts[1]
    # restricted day-of-month or day-of-week (weekly/monthly/weekday jobs):
    # interval estimation would call them daily and cry wolf — skip them
    if parts[2] != "*" or parts[4] != "*":
        return None
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


def _silence_threshold(interval_min: float) -> float:
    """How long a routine may be quiet before it is presumed dead.

    A flat 3x was tuned for a job that runs every few hours, then silently
    generalised: it gave the DAILY nightly a 72h blind window, so the Jul 15
    skip had three days to hide in. A frequent job needs slack (one miss is
    noise); for a daily job, one missed run IS the failure."""
    if interval_min >= 12 * 60:
        return interval_min + DAILY_GRACE_MINUTES
    return interval_min * LOG_SILENCE_FACTOR


def _calendar_interval_minutes(cal) -> float | None:
    """Interval implied by a launchd StartCalendarInterval (dict or list)."""
    entries = cal if isinstance(cal, list) else [cal]
    if not entries or not all(isinstance(e, dict) for e in entries):
        return None
    # weekday/monthly jobs: same cry-wolf risk as their cron cousins, skip
    if any(k in e for e in entries for k in ("Weekday", "Month", "Day")):
        return None
    if all("Hour" in e for e in entries):
        return 24 * 60.0 / len(entries)
    if all("Minute" in e for e in entries):
        return 60.0 / len(entries)
    return None


def _cron_routines() -> list[tuple]:
    """(name, interval_minutes, log_path, evidence) per scheduled crontab line."""
    out = []
    try:
        cron = subprocess.run(["crontab", "-l"], capture_output=True,
                              text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return out
    for line in cron.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        logm = re.search(r">>?\s*(\S+\.log)", line)
        interval = _cron_interval_minutes(line)
        if not logm or not interval:
            continue
        log_path = os.path.expanduser(logm.group(1))
        # relative log paths resolve against the cron line's cd, if any
        cdm = re.search(r"cd\s+(\S+)", line)
        if not os.path.isabs(log_path) and cdm:
            log_path = os.path.join(os.path.expanduser(cdm.group(1)), log_path)
        name = (re.search(r"#\s*(.+)$", line) or ["", ""])[1].strip()
        if not name:
            # An untagged line used to be named by its interpreter path, so two
            # different jobs both read as 'Routine /…/python3 silent' and no one
            # could tell which limb died. The log is unique per job, and legible.
            name = os.path.basename(log_path).rsplit(".", 1)[0]
        out.append((name, interval, log_path, line[:160]))
    return out


def _launchd_routines(agents_dir: str | None = None) -> list[tuple]:
    """Same, for scheduled LaunchAgents.

    launchd is where the reliable half of the stack lives: unlike cron, it runs
    a job the Mac slept through. That is exactly why the nightly moved here —
    and exactly why this function had to exist first. The routine exam only ever
    read `crontab -l`, so every launchd job was unwatched, and migrating a job
    to launchd silently dropped it out of the only check that covered it."""
    out = []
    d = agents_dir or os.path.expanduser("~/Library/LaunchAgents")
    for fn in sorted(glob.glob(os.path.join(d, "*.plist"))):
        try:
            with open(fn, "rb") as f:
                p = plistlib.load(f)
        except (OSError, plistlib.InvalidFileException, ValueError):
            continue
        log = p.get("StandardOutPath") or p.get("StandardErrorPath")
        if not log or not isinstance(log, str):
            continue
        if p.get("StartInterval"):
            interval = float(p["StartInterval"]) / 60
        else:
            interval = _calendar_interval_minutes(p.get("StartCalendarInterval"))
        if not interval:
            continue
        name = p.get("Label") or os.path.basename(fn)
        out.append((name, interval, os.path.expanduser(log),
                    f"{os.path.basename(fn)} (launchd, every {interval:.0f}min)"))
    return out


def routine_findings(agents_dir: str | None = None) -> list[dict]:
    out = []
    now = datetime.now().timestamp()
    for name, interval, log_path, evidence in (_cron_routines()
                                               + _launchd_routines(agents_dir)):
        if not os.path.exists(log_path):
            out.append({"key": f"routine|{log_path}|missing",
                        "finding": f"Routine '{name}' has never written its "
                                   f"log ({log_path}) — scheduled but possibly dead",
                        "severity": "warning", "evidence": evidence})
            continue
        silent_min = (now - os.path.getmtime(log_path)) / 60
        threshold = _silence_threshold(interval)
        if silent_min > threshold:
            out.append({"key": f"routine|{log_path}|silent",
                        "finding": f"Routine '{name}' silent for "
                                   f"{silent_min/60:.1f}h (runs every "
                                   f"{interval:.0f}min, presumed dead after "
                                   f"{threshold/60:.1f}h) — the stack still "
                                   f"believes in a dead limb",
                        "severity": "warning", "evidence": evidence})
    return out


# --- liveness: a STATE you assert, not an event you file once ---------------
#
# On Jul 15 the nightly consolidation did not run (the Mac slept; cron drops
# what it sleeps through) and nothing in the stack said a word. Helicon's whole
# claim is catching silent failure, and it missed its own. Three reasons:
#
#   1. the routine exam compares log mtime to 3x the interval, which gave a
#      DAILY job a 72h blind window (fixed above in _silence_threshold);
#   2. the log was a PROXY. `>>` touches it on any output, including a run that
#      died at step two — and a file's mtime is a claim the FILESYSTEM makes,
#      not one the job makes, so a manual `report > eval-latest.json`, a git
#      checkout or an editor save could vouch for a run that never happened.
#      The job now reports on itself: scripts/nightly.sh writes a run record
#      carrying its own timestamp and real exit code, and nothing else writes
#      it. The report is checked separately for being a report at all, because
#      exiting 0 is not the same as producing output;
#   3. `watch` speaks only when there is news, and findings are idempotent by
#      key, so a liveness signal filed once never fires again. Absence of an
#      alarm became indistinguishable from health.
#
# So liveness gets asserted, not inferred: nightly_status() returns a state with
# an age behind it every time it is asked, and `helicon doctor` prints it
# whether it is healthy or not. A check that only speaks on failure can itself
# die quietly — which is the failure it was hired to catch.

NIGHTLY = {
    "label": "mount-helicon-nightly",
    "cadence_hours": 24.0,
    "grace_hours": 6.0,
    "record": "nightly-run.json",    # written by scripts/nightly.sh and nothing else
    "evidence": "eval-latest.json",  # the end of the && chain
    "evidence_key": "overall",       # the report's headline metric
    "log": "nightly.log",
}


def _data_path(config: dict, name: str) -> str:
    return os.path.join(
        os.path.dirname(config.get("db_path", "data/helicon.db")), name)


def _age_hours(path: str) -> float | None:
    try:
        return (datetime.now().timestamp() - os.path.getmtime(path)) / 3600
    except OSError:
        return None


def _read_record(path: str) -> dict | None:
    """The nightly's own run record: when it ran, and what it exited with.

    A file's MTIME is not a claim the job makes — it is a claim the filesystem
    makes, and anything can make it: a manual `report > eval-latest.json`, a git
    checkout, an editor save, a restore. The record carries its timestamp INSIDE
    and is written by the nightly alone, so it cannot be forged by a passer-by."""
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        return rec if isinstance(rec, dict) and "ts" in rec else None
    except (OSError, json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return None


def _record_age_hours(rec: dict) -> float | None:
    try:
        ts = datetime.strptime(str(rec["ts"]).replace("Z", ""),
                               "%Y-%m-%dT%H:%M:%S")
    except (ValueError, KeyError, TypeError):
        return None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return (now - ts).total_seconds() / 3600


def _intact(path: str, key: str | None = None) -> bool:
    """Whether the report at `path` is a report at all.

    `>` truncates its target before the command runs, so a crash leaves a fresh
    mtime on an empty file. And exiting 0 is not the same as producing output:
    `null`, `0`, `[]`, `{}` and `{"error": ...}` all parse as JSON perfectly
    well. A report is a non-empty object carrying its headline metric."""
    try:
        if os.path.getsize(path) == 0:
            return False
        if path.endswith(".json"):
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict) or not d:
                return False
            if key and key not in d:
                return False
        return True
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False


def nightly_status(config: dict) -> dict:
    """The nightly's liveness, asserted from its own run record.

    Always returns a state: 'ok' is a claim with a timestamp, an exit code and a
    readable report behind it, never merely the absence of an alarm."""
    spec = {**NIGHTLY, **(config.get("nightly") or {})}
    rec_path, ev = _data_path(config, spec["record"]), _data_path(config, spec["evidence"])
    due = spec["cadence_hours"] + spec["grace_hours"]
    rec = _read_record(rec_path)
    age = _record_age_hours(rec) if rec else None
    st = {"label": spec["label"], "record": rec_path, "evidence": ev,
          "age_hours": age, "cadence_hours": spec["cadence_hours"],
          "due_hours": due, "exit_code": (rec or {}).get("rc"),
          "log_age_hours": _age_hours(_data_path(config, spec["log"]))}
    cad = f"cadence {spec['cadence_hours']:.0f}h"
    if rec is None:
        return {**st, "ok": False,
                "reason": f"never completed — {os.path.basename(rec_path)} has "
                          f"never been written"}
    if age is None:
        return {**st, "ok": False,
                "reason": f"unreadable run record — {os.path.basename(rec_path)} "
                          f"has no usable timestamp"}
    if rec.get("rc") != 0:
        return {**st, "ok": False,
                "reason": f"last run FAILED (exit {rec.get('rc')}) {age:.1f}h ago"}
    if not _intact(ev, spec.get("evidence_key")):
        return {**st, "ok": False,
                "reason": f"exited 0 {age:.1f}h ago but "
                          f"{os.path.basename(ev)} is empty, unreadable or not "
                          f"a report"}
    if age > due:
        return {**st, "ok": False,
                "reason": f"last completed {age:.1f}h ago, overdue by "
                          f"{age - due:.1f}h ({cad} + "
                          f"{spec['grace_hours']:.0f}h grace)"}
    return {**st, "ok": True,
            "reason": f"last completed {age:.1f}h ago ({cad}, exit 0, "
                      f"{os.path.basename(ev)} intact)"}


def nightly_findings(config: dict) -> list[dict]:
    """One finding per DAY the nightly misses. Liveness is a state, so each
    missed night is its own event — a single key filed once would mask every
    skip after the first."""
    st = nightly_status(config)
    if st["ok"]:
        return []
    day = datetime.now().date().isoformat()
    age = "never" if st["age_hours"] is None else f"{st['age_hours']:.1f}h old"
    return [{"key": f"nightly|{st['label']}|{day}",
             "finding": f"Nightly '{st['label']}' did not complete: "
                        f"{st['reason']}. The consolidation the rest of the "
                        f"stack trusts silently did not run",
             "severity": "critical",
             "evidence": f"{st['evidence']} is {age}; cadence "
                         f"{st['cadence_hours']:.0f}h"}]


# --- the hands: an MCP server that cannot speak is a dead limb too ----------
#
# Helicon audits every surface that feeds an agent — memory, standing context,
# skills, routines, output. It did not audit the surface that connects a TOOL to
# an agent, and its own was silently dead. `helicon` was registered in
# ~/.claude.json and invoked through `bash -lc`: the login profile blocks on
# stdin, and stdin IS the channel MCP speaks over, so the handshake never
# happened. 14 tools, unreachable from every session, no error anywhere. The
# product that catches silent failure could not see its own hands.
#
# The probe is the real protocol: spawn the server, send `initialize`, require
# valid JSON-RPC back. Nothing else proves a server is reachable — a process
# that starts is not a server that speaks, and the login shell proved exactly
# that distinction.

MCP_TIMEOUT_S = 20.0


def _mcp_servers(config_path: str | None = None) -> dict:
    path = config_path or os.path.join(os.path.expanduser("~"), ".claude.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("mcpServers") or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _probe_mcp(name: str, spec: dict, timeout: float = MCP_TIMEOUT_S) -> dict:
    """(ok, reason) for one stdio MCP server, by speaking MCP at it."""
    if spec.get("type", "stdio") != "stdio" or not spec.get("command"):
        return {"name": name, "ok": True, "reason": "not a stdio server — not probed"}
    cmd = [spec["command"], *(spec.get("args") or [])]
    env = {**os.environ, **(spec.get("env") or {})}
    init = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "helicon-stackwatch", "version": "1"}},
    }) + "\n"
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=env)
    except (OSError, ValueError) as e:
        return {"name": name, "ok": False, "reason": f"cannot spawn: {e}"}
    try:
        out, _ = p.communicate(init, timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        return {"name": name, "ok": False,
                "reason": f"no handshake in {timeout:.0f}s — the client times it "
                          f"out and drops every tool it serves"}
    first = next((l for l in (out or "").splitlines() if l.strip()), "")
    if not first:
        return {"name": name, "ok": False, "reason": "said nothing on stdout"}
    try:
        msg = json.loads(first)
    except json.JSONDecodeError:
        return {"name": name, "ok": False,
                "reason": f"first stdout line is not JSON-RPC, so the protocol "
                          f"is corrupt from byte one: {first[:60]!r}"}
    info = (msg.get("result") or {}).get("serverInfo") or {}
    return {"name": name, "ok": True,
            "reason": f"handshake ok ({info.get('name', '?')} "
                      f"{info.get('version', '?')})"}


def mcp_status(config_path: str | None = None) -> list[dict]:
    return [_probe_mcp(n, s) for n, s in sorted(_mcp_servers(config_path).items())]


def mcp_findings(config_path: str | None = None) -> list[dict]:
    out = []
    for st in mcp_status(config_path):
        if st["ok"]:
            continue
        out.append({"key": f"mcp|{st['name']}|dead",
                    "finding": f"MCP server '{st['name']}' is registered but "
                               f"cannot speak: {st['reason']}. Every tool it "
                               f"serves is silently missing from every session",
                    "severity": "critical",
                    "evidence": f"~/.claude.json mcpServers.{st['name']}"})
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
    for path in (os.path.expanduser("~/.claude/CLAUDE.md"),
                 os.path.abspath("CLAUDE.md")):
        if not os.path.exists(path):
            continue
        chars = len(open(path, encoding="utf-8", errors="replace").read())
        tokens = chars // 4
        if tokens > CONTEXT_BUDGET_TOKENS:
            out.append({"key": f"context|{os.path.abspath(path)}",
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
        "('routine', 'output', 'context', 'nightly', 'mcp')"
    ):
        try:
            k = json.loads(row["details"]).get("key")
            if k:
                keys.add(k)
        except (json.JSONDecodeError, TypeError):
            pass
    return keys


def stack_scan(conn: sqlite3.Connection, config: dict | None = None) -> dict:
    """Run the checks, file new findings idempotently. The nightly liveness
    check needs a config to know where its evidence lives; without one it is
    skipped rather than guessed at."""
    existing = _existing_keys(conn)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    filed = {"routine": 0, "output": 0, "context": 0, "nightly": 0, "mcp": 0}
    for kind, items in (("routine", routine_findings()),
                        ("output", output_findings(conn, ephemeral=EPHEMERAL)),
                        ("context", context_findings()),
                        ("nightly", nightly_findings(config) if config else []),
                        ("mcp", mcp_findings())):
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
