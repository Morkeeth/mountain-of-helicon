"""helicon watch — drift notifies YOU.

The original dictated ask: "at any drift we need to be notified." Everything
else in this repo answers a question you asked; watch answers the one you
didn't. It runs the full loop headlessly (scan -> decay -> pair selector ->
alias triage -> rot exam), diffs the result against the last run, and speaks
ONLY when something is new: fresh audit findings, or a rot class flipping
CLEAN -> ROT FOUND. No news = no output, no notification, nothing to ignore.

State is a cursor (last seen audit_log id + last rot verdicts), kept in a
JSON file next to the DB — it is bookkeeping about the watcher, not memory,
so it does not live in the store.

Delivery: a drift-report.md written where config points (default data/,
point it at an Obsidian dashboard to make drift a note that greets you), and
a macOS notification when there is something to say. `--install` writes the
crontab line, people-radar style; `--uninstall` removes it.
"""
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

CRON_TAG = "# mount-helicon-watch"


def _state_path(config: dict) -> str:
    return os.path.join(os.path.dirname(config["db_path"]), "watch-state.json")


def load_state(config: dict) -> dict:
    try:
        with open(_state_path(config)) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"last_audit_id": 0, "rot_verdicts": {}, "last_run": None}


def save_state(config: dict, state: dict):
    # atomic: a crash mid-write must not corrupt the cursor (a corrupt state
    # file silently re-baselines and swallows pending drift)
    path = _state_path(config)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def collect_drift(conn: sqlite3.Connection, state: dict,
                  repo_root: str | None = None,
                  config: dict | None = None) -> dict:
    """Everything new since the cursor: fresh audit findings + rot class
    flips. Pure read; the caller decides whether to speak."""
    from helicon.rot import run_rot_exam

    last_id = state.get("last_audit_id", 0)
    rows = conn.execute(
        "SELECT id, audit_type, finding, severity FROM audit_log "
        "WHERE id > ? AND human_decision IS NULL AND machine_decision IS NULL "
        "ORDER BY id", (last_id,),
    ).fetchall()
    max_row = conn.execute("SELECT MAX(id) m FROM audit_log").fetchone()
    max_id = max(max_row["m"] or 0, last_id)

    exam = run_rot_exam(conn, repo_root, config=config)
    old = state.get("rot_verdicts", {})
    flips = []
    for c in exam["checks"]:
        prev = old.get(c["id"])
        if prev is not None and prev != c["verdict"]:
            flips.append({"id": c["id"], "name": c["name"],
                          "from": prev, "to": c["verdict"],
                          "receipt": c["receipt"]})
    verdicts = {c["id"]: c["verdict"] for c in exam["checks"]}

    return {
        "new_findings": [dict(r) for r in rows],
        "flips": flips,
        "rot_found": exam["rot_found"],
        "max_audit_id": max_id,
        "rot_verdicts": verdicts,
    }


def format_drift_report(drift: dict, ran_scan: bool, now: str) -> str:
    lines = [
        "# Mountain of Helicon — drift report",
        "",
        f"_{now} · scan {'ran' if ran_scan else 'skipped'} · "
        f"{drift['rot_found']}/10 rot classes showing rot_",
        "",
    ]
    if drift["flips"]:
        lines.append("## Rot class flips")
        for f in drift["flips"]:
            lines.append(f"- **{f['id']} {f['name']}**: {f['from']} → {f['to']}")
            lines.append(f"  - {f['receipt']}")
        lines.append("")
    if drift["new_findings"]:
        lines.append(f"## New findings ({len(drift['new_findings'])})")
        for r in drift["new_findings"]:
            lines.append(f"- [{r['severity']}] {r['audit_type']}: {r['finding']}")
        lines.append("")
    lines.append("Run `helicon rot` for the full exam, `helicon serve` for FINDINGS.")
    return "\n".join(lines)


def notify_macos(title: str, message: str) -> bool:
    """Best-effort notification; watch must never crash because a desktop
    was not listening."""
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{message}" with title "{title}"'],
            capture_output=True, timeout=10, check=False)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def watch_once(conn: sqlite3.Connection, config: dict, scan: bool = True,
               notify: bool = True, repo_root: str | None = None) -> dict:
    """One watch tick. Scans (unless told not to), files pairing/alias
    findings, diffs against the cursor, speaks only on news, advances the
    cursor. Returns what happened either way (for --json and tests)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    state = load_state(config)

    ran_scan = False
    if scan and config.get("connectors"):
        from helicon.scanner import run_scan
        run_scan(config)
        ran_scan = True

    # The selectors file new findings idempotently; the diff picks them up.
    from helicon.pairing import pair_scan
    from helicon.claims import claim_scan
    from helicon.aliases import alias_scan
    client = None
    try:
        from helicon.qwen import get_client, set_cache_db
        set_cache_db(conn)
        client = get_client(config)
    except Exception:
        pass
    pair_scan(conn, client=client)
    claim_scan(conn, config)
    alias_scan(conn, config=config)
    from helicon.stackwatch import stack_scan
    stack_scan(conn, config)

    drift = collect_drift(conn, state, repo_root, config=config)
    # First run ever = baseline: set the cursor silently. A store with months
    # of open findings should not greet its new watcher with all of them.
    baseline = state.get("last_run") is None
    spoke = (not baseline) and bool(drift["new_findings"] or drift["flips"])

    report_path, report_error = None, None
    if spoke:
        try:
            report_dir = os.path.expanduser(
                config.get("watch", {}).get("report_dir")
                or os.path.dirname(config["db_path"]))
            os.makedirs(report_dir, exist_ok=True)
            report_path = os.path.join(report_dir, "drift-report.md")
            with open(report_path, "w") as f:
                f.write(format_drift_report(drift, ran_scan, now))
        except OSError as e:
            # a bad report_dir must not crashloop the cron tick before the
            # cursor advances — record the failure, keep the tick alive
            report_path, report_error = None, str(e)
        if notify:
            flips = len(drift["flips"])
            notify_macos(
                "Mountain of Helicon",
                f"{len(drift['new_findings'])} new finding(s)"
                + (f", {flips} rot class flip(s)" if flips else "")
                + " — drift-report.md")

    save_state(config, {
        "last_audit_id": drift["max_audit_id"],
        "rot_verdicts": drift["rot_verdicts"],
        "last_run": now,
    })

    return {
        "ran_scan": ran_scan,
        "baseline": baseline,
        "new_findings": len(drift["new_findings"]),
        "flips": drift["flips"],
        "rot_found": drift["rot_found"],
        "spoke": spoke,
        "report_path": report_path,
        "report_error": report_error,
    }


def _cron_line(repo_root: str, every_hours: int) -> str:
    py = sys.executable
    return (f"0 */{every_hours} * * * cd {repo_root} && "
            f"{py} -m helicon.cli watch --quiet >> data/watch.log 2>&1 {CRON_TAG}")


def install_cron(repo_root: str, every_hours: int = 6) -> str:
    """Idempotent: replaces any previous mount-helicon-watch line."""
    current = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    lines = [l for l in (current.stdout or "").splitlines()
             if CRON_TAG not in l]
    line = _cron_line(repo_root, every_hours)
    lines.append(line)
    subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n",
                   text=True, check=True)
    return line


def uninstall_cron() -> bool:
    current = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    lines = (current.stdout or "").splitlines()
    kept = [l for l in lines if CRON_TAG not in l]
    if len(kept) == len(lines):
        return False
    subprocess.run(["crontab", "-"], input="\n".join(kept) + "\n",
                   text=True, check=True)
    return True
