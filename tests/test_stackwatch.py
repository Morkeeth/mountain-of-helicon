"""Stackwatch: routines, dead paths, context weight — the harness under the exam."""
import pytest

from helicon.db import init_db, insert_cube
from helicon.models import ConnectorResult
from helicon.scanner import result_to_cube
from helicon.stackwatch import (
    _cron_interval_minutes, output_findings, stack_scan,
)


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "helicon.db"))


def _claim_cube(conn, path, when="now"):
    r = ConnectorResult(
        source="claude-code", source_ref="session_x", type="file_created",
        title=f"Created: {path.split('/')[-1]}",
        content=f"File: {path}\nsome body",
        created_at=__import__("datetime").datetime.utcnow().isoformat())
    cube = result_to_cube(r)
    assert insert_cube(conn, cube)
    conn.commit()
    return cube.id


def test_cron_interval_parsing():
    assert _cron_interval_minutes("*/30 * * * * x") == 30
    assert _cron_interval_minutes("0 */6 * * * x") == 360
    assert _cron_interval_minutes("15 * * * * x") == 60
    assert _cron_interval_minutes("bad") is None


def test_dead_path_is_a_finding_ephemeral_is_not(conn, tmp_path):
    real = tmp_path / "exists.md"
    real.write_text("hi")
    _claim_cube(conn, str(real))                      # exists -> no finding
    _claim_cube(conn, str(tmp_path / "gone.md"))      # missing -> finding
    _claim_cube(conn, "/tmp/ephemeral/scratch.md")    # ephemeral -> excluded
    got = output_findings(conn, ephemeral=('/tmp/',))
    assert len(got) == 1
    assert "gone.md" in got[0]["finding"]
    assert "dead path" in got[0]["finding"]


def test_stack_scan_files_once(conn, tmp_path):
    import helicon.stackwatch as SW
    _claim_cube(conn, str(tmp_path / "vanished.md"))
    orig = SW.EPHEMERAL
    SW.EPHEMERAL = ("/tmp/",)
    try:
        first = stack_scan(conn)
        assert first["output"] == 1
        assert stack_scan(conn)["output"] == 0  # idempotent
    finally:
        SW.EPHEMERAL = orig
    n = conn.execute("SELECT COUNT(*) FROM audit_log "
                     "WHERE audit_type='output'").fetchone()[0]
    assert n == 1


def test_cron_interval_skips_dow_dom_restricted_jobs():
    """P1: weekly/monthly jobs were being called daily -> false dead-limb
    findings every Thursday."""
    assert _cron_interval_minutes("0 0 * * 0 job") is None       # weekly
    assert _cron_interval_minutes("0 0 1 * * job") is None       # monthly
    assert _cron_interval_minutes("15 3 * * 1-5 job") is None    # weekdays
    assert _cron_interval_minutes("*/30 * * * * job") == 30      # still works


def test_concurrent_double_file_blocked_by_unique_index(conn, tmp_path):
    """P1: watch cron + evolve racing the same selector must not double-file.
    The read-then-insert dedup loses the race; the unique index wins it."""
    import sqlite3 as s3
    from helicon.db import insert_audit
    from helicon.models import AuditResult
    a = AuditResult(audit_type="output", target_type="stack", target_id="k",
                    finding="x", severity="warning",
                    details={"key": "output|/race"}, audited_at="2026-07-06")
    assert insert_audit(conn, a) is not None
    assert insert_audit(conn, a) is None  # second filer rejected, no raise


# --- liveness: the Jul 15 skip, and each reason nothing caught it ------------
import json
import os
import time

from helicon.stackwatch import (
    DAILY_GRACE_MINUTES, LOG_SILENCE_FACTOR, _launchd_routines,
    _silence_threshold, nightly_findings, nightly_status, routine_findings,
)

PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.test.nightly</string>
<key>StartCalendarInterval</key><dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>47</integer></dict>
<key>StandardOutPath</key><string>{log}</string>
</dict></plist>"""


def _nightly_env(tmp_path, age_hours=None, rc=0, report='{"overall": 74.2}'):
    """A nightly that ran `age_hours` ago and exited `rc`, with its report."""
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    config = {"db_path": str(data / "helicon.db")}
    if report is not None:
        (data / "eval-latest.json").write_text(report)
    if age_hours is not None:
        import datetime as _dt
        ts = (_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
              - _dt.timedelta(hours=age_hours)).strftime("%Y-%m-%dT%H:%M:%S")
        (data / "nightly-run.json").write_text(
            json.dumps({"ts": ts, "rc": rc, "host": "test"}))
    return config, data


def test_a_daily_job_alarms_after_one_missed_run_not_three():
    """THE calibration bug: a flat 3x factor gave the daily nightly a 72h blind
    window, so a skip had three days to hide. One missed night IS the failure."""
    daily = 24 * 60.0
    assert _silence_threshold(daily) == daily + DAILY_GRACE_MINUTES
    assert _silence_threshold(daily) / 60 == 30.0
    # the real Jul 15 skip: 31h silent. Invisible at 3x, caught now.
    assert 31 * 60 > _silence_threshold(daily)
    assert 31 * 60 < daily * LOG_SILENCE_FACTOR, "3x would still have missed it"
    # a frequent job keeps its slack — one miss there is noise, not death
    assert _silence_threshold(360.0) == 360.0 * LOG_SILENCE_FACTOR


def test_launchd_jobs_are_watched_at_all(tmp_path):
    """Every launchd job was unwatched: the exam only read `crontab -l`. Moving
    the nightly to launchd would have dropped it out of its only check."""
    agents, log = tmp_path / "agents", tmp_path / "n.log"
    agents.mkdir()
    log.write_text("ran")
    (agents / "com.test.nightly.plist").write_text(PLIST.format(log=log))
    found = _launchd_routines(str(agents))
    assert len(found) == 1
    name, interval, log_path, _ = found[0]
    assert name == "com.test.nightly"
    assert interval == 24 * 60.0          # StartCalendarInterval Hour+Minute
    assert log_path == str(log)


def test_nightly_overdue_is_caught_and_named(tmp_path):
    config, _ = _nightly_env(tmp_path, age_hours=31)
    st = nightly_status(config)
    assert st["ok"] is False
    assert "overdue by 1.0h" in st["reason"]
    assert nightly_findings(config)[0]["severity"] == "critical"


def test_nightly_healthy_asserts_an_age_rather_than_silence(tmp_path):
    """'ok' must be a claim with evidence behind it. A check that only speaks on
    failure cannot be distinguished from a check that died."""
    config, _ = _nightly_env(tmp_path, age_hours=8)
    st = nightly_status(config)
    assert st["ok"] is True
    assert "last completed 8.0h ago" in st["reason"]
    assert st["age_hours"] == pytest.approx(8.0, abs=0.1)
    assert nightly_findings(config) == []


def test_a_nightly_that_never_ran_is_not_healthy(tmp_path):
    config, _ = _nightly_env(tmp_path, age_hours=None)
    st = nightly_status(config)
    assert st["ok"] is False and "never completed" in st["reason"]


def test_each_missed_night_is_its_own_event(tmp_path):
    """Findings are idempotent by key, so one key filed once would mask every
    skip after the first. Liveness is a state: key by the day it was missed."""
    config, _ = _nightly_env(tmp_path, age_hours=31)
    key = nightly_findings(config)[0]["key"]
    import datetime as _dt
    assert key.endswith(_dt.date.today().isoformat())


# --- what the adversarial pass broke in the liveness check itself ------------
# The first probe read eval-latest.json's MTIME. But an mtime is a claim the
# FILESYSTEM makes, not one the job makes, and exiting 0 is not the same as
# producing output. Both let a dead nightly read as healthy.

def test_a_failed_run_is_not_healthy(tmp_path):
    """The chain's exit code is a fact the nightly reports about itself. Under
    the mtime probe, a run that failed AFTER touching its artifact read green."""
    config, _ = _nightly_env(tmp_path, age_hours=1, rc=1)
    st = nightly_status(config)
    assert st["ok"] is False
    assert "FAILED (exit 1)" in st["reason"]
    assert nightly_findings(config)[0]["severity"] == "critical"


@pytest.mark.parametrize("garbage", ["null", "0", "[]", "{}", "false",
                                     '"error: qwen api 401"',
                                     '{"error": "traceback"}'])
def test_valid_json_that_is_not_a_report_is_not_healthy(tmp_path, garbage):
    """Every one of these parses as JSON perfectly well. `report` can exit 0 and
    still emit an error object (Qwen 401, no eval data) — a report is a
    non-empty object carrying its headline metric."""
    config, _ = _nightly_env(tmp_path, age_hours=1, report=garbage)
    st = nightly_status(config)
    assert st["ok"] is False, f"{garbage} passed as a healthy report"
    assert "not a report" in st["reason"]


def test_touching_the_report_cannot_forge_health(tmp_path):
    """A manual `report > eval-latest.json`, a git checkout or an editor save
    used to buy 30h of fake health. The record carries its timestamp INSIDE, so
    the filesystem cannot vouch for a run that never happened."""
    config, data = _nightly_env(tmp_path, age_hours=40)      # 40h = overdue
    assert nightly_status(config)["ok"] is False
    ev = data / "eval-latest.json"
    ev.write_text('{"overall": 74.2}')                       # fresh mtime, now
    os.utime(ev, None)
    st = nightly_status(config)
    assert st["ok"] is False, "a touched artifact forged a healthy nightly"
    assert "overdue by 10.0h" in st["reason"]


def test_a_missing_run_record_is_never_healthy(tmp_path):
    config, _ = _nightly_env(tmp_path, age_hours=None)
    assert nightly_status(config)["ok"] is False


def test_nightly_status_survives_a_config_without_db_path(tmp_path, monkeypatch):
    """doctor is the front door; a KeyError here takes the whole health check
    down with it. chdir because the db_path default is RELATIVE — without it
    this reads the real repo's data/ and passes for the wrong reason."""
    monkeypatch.chdir(tmp_path)
    assert nightly_status({})["ok"] is False


# --- the wiring, not just the parts -----------------------------------------

def test_routine_findings_actually_merges_launchd(tmp_path, monkeypatch):
    """Deleting `+ _launchd_routines(...)` from routine_findings re-orphans every
    launchd job — and every other test still passed. Pin the WIRING: a stale
    launchd job must produce a finding through the public entry point."""
    monkeypatch.setattr("helicon.stackwatch._cron_routines", lambda: [])
    agents, log = tmp_path / "agents", tmp_path / "n.log"
    agents.mkdir()
    log.write_text("ran once")
    old = time.time() - 40 * 3600
    os.utime(log, (old, old))
    (agents / "com.test.nightly.plist").write_text(PLIST.format(log=log))
    found = routine_findings(str(agents))
    assert len(found) == 1, "launchd job invisible to the public entry point"
    assert "com.test.nightly" in found[0]["finding"]
    assert "silent for 40.0h" in found[0]["finding"]


def test_a_daily_job_31h_silent_is_flagged_through_the_entry_point(tmp_path, monkeypatch):
    """The real Jul 15 shape, end to end: 31h silent on a daily cadence. Under
    the flat 3x factor this produced NO finding for another 41 hours."""
    monkeypatch.setattr("helicon.stackwatch._cron_routines", lambda: [])
    agents, log = tmp_path / "agents", tmp_path / "n.log"
    agents.mkdir()
    log.write_text("ran")
    old = time.time() - 31 * 3600
    os.utime(log, (old, old))
    (agents / "com.test.nightly.plist").write_text(PLIST.format(log=log))
    assert 31 * 60 < 24 * 60 * LOG_SILENCE_FACTOR, "3x would not have caught it"
    assert len(routine_findings(str(agents))) == 1
