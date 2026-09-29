import json
import sqlite3
from datetime import datetime, timezone

from helicon.overview_status import build_overview


def seeded(tmp_path, eval_at="2026-09-28T12:00:00"):
    db = tmp_path / "helicon.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE helicon_cubes (
            id TEXT, type TEXT, created_at TEXT, last_reinforced TEXT,
            review_status TEXT, merged_into TEXT
        );
        CREATE TABLE scan_log (
            id INTEGER, completed_at TEXT, connectors_used TEXT, errors TEXT
        );
        CREATE TABLE eval_runs (
            id INTEGER, run_at TEXT, query_count INTEGER, details TEXT
        );
        CREATE TABLE audit_log (
            id INTEGER, audit_type TEXT, severity TEXT, audited_at TEXT,
            resolved_at TEXT, human_decision TEXT, machine_decision TEXT
        );
        CREATE TABLE entity_aliases (id INTEGER);
        CREATE TABLE rules (id INTEGER);
    """)
    conn.executemany("INSERT INTO helicon_cubes VALUES (?,?,?,?,?,?)", [
        ("fresh", "decision", "2026-09-20T00:00:00", "", "pending", None),
        ("stale", "decision", "2026-07-01T00:00:00", "", "pending", None),
        ("ungraded", "rule", "2020-01-01T00:00:00", "", "pending", None),
    ])
    conn.execute("INSERT INTO scan_log VALUES (1,?,?,?)", (
        "2026-09-29T10:00:00", json.dumps(["git", "obsidian"]), "[]"))
    details = {"retrieval": [
        {"found_at_rank": 1, "top_3_titles": ["one"]},
        {"found_at_rank": None, "top_3_titles": ["other"]},
    ]}
    conn.execute("INSERT INTO eval_runs VALUES (1,?,?,?)", (eval_at, 2, json.dumps(details)))
    conn.executemany("INSERT INTO audit_log VALUES (?,?,?,?,?,?,?)", [
        (1, "factual", "critical", "2026-09-01T00:00:00", "2026-09-02T00:00:00", "resolved:true", None),
        (2, "identity", "critical", "2026-09-03T00:00:00", None, None, None),
    ])
    conn.commit()
    conn.close()

    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "feedback_real.md").write_text("source\n")
    (tmp_path / "GOLDEN_RULES.md").write_text(
        "## Rules\n- first\n_[ruling on finding #1, 2026-09-02]_\n"
        "- second\n_[feedback_real.md]_\n"
    )
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "db_path": str(db),
        "connectors": {
            "git": {"enabled": True},
            "obsidian": {"enabled": True},
            "claude-code": {"enabled": False, "memory_dir": str(memory)},
        },
    }))
    return config


def test_overview_keeps_five_real_denominators_separate(tmp_path):
    config = seeded(tmp_path)
    report = build_overview(
        home=tmp_path, project=tmp_path, config_path=config,
        now=datetime(2026, 9, 29, 12, tzinfo=timezone.utc),
    )
    metrics = {item["id"]: item for item in report["metrics"]}
    assert list(metrics) == ["freshness", "coverage", "retrieval", "drift", "rules"]
    assert (metrics["freshness"]["numerator"], metrics["freshness"]["denominator"]) == (1, 2)
    assert (metrics["coverage"]["numerator"], metrics["coverage"]["denominator"]) == (2, 2)
    assert (metrics["retrieval"]["numerator"], metrics["retrieval"]["denominator"]) == (1, 2)
    assert (metrics["drift"]["numerator"], metrics["drift"]["denominator"]) == (1, 2)
    assert (metrics["rules"]["numerator"], metrics["rules"]["denominator"]) == (2, 2)
    assert "overall" not in report
    assert report["setup_drift"]["status"] == "tracking_started"


def test_old_retrieval_evidence_is_unmeasured_but_history_remains(tmp_path):
    config = seeded(tmp_path, eval_at="2026-08-01T12:00:00")
    report = build_overview(
        home=tmp_path, project=tmp_path, config_path=config,
        now=datetime(2026, 9, 29, 12, tzinfo=timezone.utc),
    )
    retrieval = next(item for item in report["metrics"] if item["id"] == "retrieval")
    assert retrieval["state"] == "unmeasured"
    assert retrieval["value"] is None
    assert retrieval["points"][0]["value"] == 50.0
    assert "older than 30 days" in retrieval["limit"]


def test_missing_store_never_becomes_a_zero(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"db_path": str(tmp_path / "missing.db")}))
    report = build_overview(home=tmp_path, project=tmp_path, config_path=config)
    assert all(item["state"] == "unmeasured" for item in report["metrics"])
    assert all(item["value"] is None for item in report["metrics"])
