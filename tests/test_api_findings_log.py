"""/api/findings and /api/log: FastAPI TestClient against a temp seeded SQLite
DB. Findings aggregate the real audit pipeline (audit_temporal/audit_decay run
on seeded cubes, results written via insert_audit); the log merges audit_log,
human reviews, triage_log, and superseded reconciliation batches. Battery
findings are behind ?include=battery so the default response stays fast; the
skills scan is pointed at an empty root so nothing depends on the host's
~/.claude/skills."""
import hashlib
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from helicon.audit import audit_decay, audit_temporal
from helicon.db import init_db, insert_audit, insert_cube, insert_review
from helicon.models import HeliconCube, Review
from helicon.triage import init_triage_table

NOW = datetime.utcnow()
STALE_CONTENT = (
    "Ship the demo today, the deadline is this week. "
    + "Detailed plan for the demo video recording and upload steps. " * 10
)

FINDING_FIELDS = {
    "id", "kind", "severity", "title", "why", "evidence_preview",
    "source", "source_ref", "cube_id", "suggested_action", "created_at",
}


def _cube(cid: str, title: str, content: str, *, age_days: float = 0.0,
          confidence: float = 1.0, source: str = "claude-code") -> HeliconCube:
    created = (NOW - timedelta(days=age_days)).isoformat()
    return HeliconCube(
        id=cid,
        source=source,
        source_ref=f"{source}/{cid}",
        type="memory",
        title=title,
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        created_at=created,
        valid_from=created,
        confidence=confidence,
    )


def _seed(conn):
    # stale + time-relative -> temporal audit finding (28d old, says "today")
    insert_cube(conn, _cube("cube-stale", "Demo plan", STALE_CONTENT, age_days=28))
    # decayed to ~0 -> decay audit finding (critical: confidence <= 0.01)
    insert_cube(conn, _cube("cube-decayed", "Old scratch note",
                            "temporary note about an abandoned spike",
                            age_days=60, confidence=0.005))
    # human-reviewed cube + review receipt with notes
    insert_cube(conn, _cube("cube-kept", "Deploy checklist",
                            "1. build 2. rotate key 3. deploy", age_days=3))
    insert_review(conn, Review(
        id=None, cube_id="cube-kept", decision="approved",
        notes="canonical, keep", reviewed_at=NOW.isoformat(),
    ))

    # real audit pipeline writes the findings the API must aggregate
    for result in audit_temporal(conn, stale_days=7) + audit_decay(conn):
        insert_audit(conn, result)

    # reconciliation batch: two superseded cubes from the same source
    for i in (1, 2):
        insert_cube(conn, _cube(f"cube-super-{i}", f"Old rule {i}",
                                f"rule text that was edited away {i}",
                                age_days=10, source="agent-rules"))
    conn.execute(
        "UPDATE helicon_cubes SET review_status = 'superseded' "
        "WHERE id IN ('cube-super-1', 'cube-super-2')"
    )

    # auto-triage receipt
    conn.execute(
        "INSERT INTO triage_log (cube_id, action, reason, rule_confidence, triaged_at) "
        "VALUES ('cube-decayed', 'kill', '3 items below 5% confidence (Weibull decay)', "
        "0.8, ?)",
        (NOW.isoformat(),),
    )
    conn.commit()


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "helicon.db")
    conn = init_db(db_path)
    init_triage_table(conn)
    _seed(conn)
    conn.close()

    monkeypatch.delenv("HELICON_PASSWORD", raising=False)
    monkeypatch.setattr("helicon.api.app.load_config", lambda: {"db_path": db_path})
    # hermetic: don't scan the host machine's real skills library
    monkeypatch.setattr("helicon.api.findings._SKILL_ROOTS", [])

    from helicon.api.app import create_app
    with TestClient(create_app()) as c:
        yield c


def test_findings_default_aggregates_audit_kinds(client):
    data = client.get("/api/findings").json()
    findings, summary = data["findings"], data["summary"]

    assert summary["total"] == len(findings) > 0
    assert summary["by_kind"].get("temporal") == 1
    assert summary["by_kind"].get("decay") == 1
    assert set(summary["by_severity"]) <= {"critical", "warning", "info"}

    for f in findings:
        assert FINDING_FIELDS <= set(f), f

    temporal = next(f for f in findings if f["kind"] == "temporal")
    assert temporal["cube_id"] == "cube-stale"
    assert temporal["title"] == "Demo plan"
    assert temporal["why"].startswith("Freshness:")
    assert "28 days old" in temporal["why"] and "today" in temporal["why"]
    assert temporal["suggested_action"] == "kill_stale"
    assert temporal["source"] == "claude-code"
    assert temporal["source_ref"] == "claude-code/cube-stale"
    # evidence: first ~300 chars of the actual cube content
    assert temporal["evidence_preview"] == STALE_CONTENT[:300]
    assert 0 < len(temporal["evidence_preview"]) <= 300

    decay = next(f for f in findings if f["kind"] == "decay")
    assert decay["cube_id"] == "cube-decayed"
    assert decay["severity"] == "critical"
    assert decay["suggested_action"] == "kill_stale"

    # sorted severity desc: the critical decay finding outranks the warning
    assert findings[0]["severity"] == "critical"


def test_findings_default_excludes_battery(client):
    data = client.get("/api/findings").json()
    assert "battery" not in data["summary"]["by_kind"]
    assert all(f["kind"] != "battery" for f in data["findings"])


def test_findings_kind_filter_and_limit(client):
    data = client.get("/api/findings", params={"kind": "temporal"}).json()
    assert data["summary"]["total"] == 1
    assert [f["kind"] for f in data["findings"]] == ["temporal"]

    data = client.get("/api/findings", params={"limit": 1}).json()
    assert len(data["findings"]) == 1
    assert data["summary"]["total"] > 1  # summary counts the full set


def test_findings_include_battery_is_explicit(client):
    # tiny DB -> no benchmark queries, but the lazy path must run cleanly
    resp = client.get("/api/findings", params={"include": "battery"})
    assert resp.status_code == 200
    assert "findings" in resp.json()


def test_log_returns_receipts_newest_first(client):
    data = client.get("/api/log").json()
    entries = data["entries"]
    assert data["total"] == len(entries) > 0

    for e in entries:
        assert {"ts", "actor", "action", "detail"} <= set(e)
        assert e["actor"] in ("human", "helicon", "qwen")

    tss = [e["ts"] for e in entries]
    assert tss == sorted(tss, reverse=True)

    actions = [e["action"] for e in entries]
    # helicon flagged the temporal + decay findings
    assert "audit_flag_temporal" in actions and "audit_flag_decay" in actions
    # human review receipt carries the decision verb and the notes
    review = next(e for e in entries if e["action"] == "review_kept")
    assert review["actor"] == "human"
    assert "Deploy checklist" in review["detail"]
    assert "canonical, keep" in review["detail"]
    # auto-triage receipt
    triage = next(e for e in entries if e["action"] == "triage_kill")
    assert triage["actor"] == "helicon"
    assert "Weibull" in triage["detail"]


def test_log_includes_superseded_batch(client):
    entries = client.get("/api/log").json()["entries"]
    batch = next(e for e in entries if e["action"] == "reconcile_superseded")
    assert batch["actor"] == "helicon"
    assert batch["count"] == 2
    assert "agent-rules" in batch["detail"]


def test_log_limit(client):
    entries = client.get("/api/log", params={"limit": 2}).json()["entries"]
    assert len(entries) == 2
