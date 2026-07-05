"""GOLDEN RULES: the stack's law, compiled from human judgment with provenance."""
import json
import os

import pytest

from helicon.aliases import add_alias
from helicon.db import init_db, insert_audit
from helicon.gold import compile_gold, gather, gold_history, inject, write_gold
from helicon.models import AuditResult


@pytest.fixture
def env(tmp_path):
    db = str(tmp_path / "data" / "helicon.db")
    conn = init_db(db)
    config = {"db_path": db,
              "claims": {"canonical": {"wins": "mindmap.md"}}}
    add_alias(conn, "oldname", "newname", "2026-07-01T00:00:00", note="test")
    conn.execute("INSERT INTO rules (nl_text, predicate, action, status, "
                 "created_at, approved_at, trust) VALUES "
                 "('kill drafts older than 60 days', '{}', 'kill', 'approved', "
                 "'2026-07-01', '2026-07-02', 0.9)")
    insert_audit(conn, AuditResult(
        audit_type="factual", target_type="cube", target_id="gc_x",
        finding="Cross-source contradiction: Avery birthday 05-13 vs 05-18",
        severity="critical", human_decision="resolved:05-18",
        details={"pair_key": "k", "person": "avery", "topic": "birthday",
                 "dates": ["05-13", "05-18"]},
        audited_at="2026-07-05", resolved_at="2026-07-05T10:00:00"))
    insert_audit(conn, AuditResult(
        audit_type="factual", target_type="cube", target_id="gc_y",
        finding="Cross-source contradiction: Paris birthday",
        severity="warning", human_decision="dismissed",
        details={"pair_key": "k2", "dismiss_reason": "place-as-person bug, fixed"},
        audited_at="2026-07-05", resolved_at="2026-07-05T11:00:00"))
    conn.commit()
    return conn, config


def test_every_rule_has_provenance(env):
    conn, config = env
    g = gather(conn, config)
    assert g["canon"] and g["renames"] and g["triage"]
    assert g["resolutions"] and g["precedents"]
    for section in g.values():
        for item in section:
            assert item.get("prov")


def test_compiled_law_reads_like_law(env):
    conn, config = env
    md = compile_gold(conn, config)
    assert "GOLDEN RULES" in md
    assert "avery birthday = 05-18" in md
    assert "oldname -> newname" in md
    assert "NOT rot: " in md
    assert "kill drafts older than 60 days" in md
    assert "A rule without provenance is a vibe" in md


def test_write_appends_history(env):
    conn, config = env
    a = write_gold(conn, config)
    assert os.path.exists(a["path"])
    add_alias(conn, "b", "c", "2026-07-02T00:00:00")
    b = write_gold(conn, config)
    assert b["total"] == a["total"] + 1
    hist = gold_history(config)
    assert [h["total"] for h in hist] == [a["total"], b["total"]]


def test_inject_is_dry_run_by_default(env, tmp_path, monkeypatch):
    conn, config = env
    monkeypatch.setenv("HOME", str(tmp_path))
    res = inject(conn, config, apply=False)
    assert res["applied"] is False
    assert not os.path.exists(res["target"])
    res = inject(conn, config, apply=True)
    assert os.path.exists(res["target"])
    # second apply keeps a .bak of the first
    inject(conn, config, apply=True)
    assert os.path.exists(res["target"] + ".bak")
