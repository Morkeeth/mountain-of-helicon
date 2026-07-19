"""Integration tests at the real HTTP boundary the dashboard calls. These pin the
failure paths a user would otherwise have to monitor by hand: the API must never
report success on a failure, must reject invalid state, and must persist what it
claims. (Unit tests call the functions; these drive the wire.)"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from helicon.demo import seed


@pytest.fixture
def client(tmp_path, monkeypatch):
    import helicon.api.app as app_mod
    db = str(tmp_path / "demo.db")
    seed(db)  # creates the schema + seeds the demo store
    # TestClient runs the app in a worker thread; share one cross-thread conn so
    # the app and the test assertions read the same live state.
    conn = sqlite3.connect(db, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    monkeypatch.setattr(app_mod, "get_conn", lambda: conn)
    monkeypatch.setattr(app_mod, "get_config", lambda: {"db_path": db})
    return TestClient(app_mod.app), conn


def _identity_id(conn):
    return conn.execute("SELECT id FROM audit_log WHERE audit_type='identity' AND human_decision IS NULL LIMIT 1").fetchone()["id"]


def test_apply_persists_what_it_claims(client):
    c, conn = client
    fid = _identity_id(conn)
    r = c.post("/api/govern/apply-batch", json={"rulings": [
        {"finding_id": fid, "verb": "rule_identity", "payload": {"canonical": "a payments protocol"}}]})
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] == 1 and body["receipt"][0]["applied"]
    # the claim is backed by persisted state, queried fresh over the same boundary
    assert conn.execute("SELECT human_decision FROM audit_log WHERE id=?", (fid,)).fetchone()["human_decision"]


def test_apply_never_reports_success_on_a_bad_ruling(client):
    c, conn = client
    r = c.post("/api/govern/apply-batch", json={"rulings": [
        {"finding_id": 999999, "verb": "rule_identity", "payload": {"canonical": "x"}}]})
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] == 0 and body["failed"] == 1
    assert body["receipt"][0]["applied"] is False and body["receipt"][0]["error"]


def test_empty_batch_is_rejected_not_silently_ok(client):
    c, _ = client
    assert c.post("/api/govern/apply-batch", json={"rulings": []}).status_code == 400


def test_double_undo_is_prevented(client):
    c, conn = client
    fid = _identity_id(conn)
    tok = c.post("/api/govern/apply-batch", json={"rulings": [
        {"finding_id": fid, "verb": "rule_identity", "payload": {"canonical": "a payments protocol"}}]}).json()["undo_token"]
    assert c.post("/api/govern/undo-batch", json={"undo_token": tok}).status_code == 200
    # a second undo (double-click, back-button, retry) must not double-reverse
    assert c.post("/api/govern/undo-batch", json={"undo_token": tok}).status_code == 400
    assert c.post("/api/govern/undo-batch", json={"undo_token": "gb_does_not_exist"}).status_code == 404
