from fastapi import FastAPI
from fastapi.testclient import TestClient

from helicon.api import correction_transfer as api


def client():
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    return TestClient(app, base_url="http://127.0.0.1:8420")


def headers():
    return {"X-Helicon-Local": "1"}


def test_example_is_read_only_and_full_journey_is_inspectable(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "helicon_home", lambda: str(tmp_path))
    c = client()

    example = c.get("/api/correction-transfer/example", headers=headers())
    assert example.status_code == 200
    assert list(tmp_path.iterdir()) == []

    fields = {key: value for key, value in example.json().items() if key != "cases"}
    proposal = c.post("/api/correction-transfer/proposals", json=fields, headers=headers())
    assert proposal.status_code == 200, proposal.text
    proposed = proposal.json()
    assert proposed["status"] == "proposed"

    accepted = c.post(
        f"/api/correction-transfer/{proposed['id']}/decision",
        json={"decision": "accept"},
        headers=headers(),
    )
    assert accepted.status_code == 200
    comparison = c.post(
        "/api/correction-transfer/compare",
        json={"cases": example.json()["cases"]},
        headers=headers(),
    )
    assert comparison.status_code == 200
    relevant, unrelated = comparison.json()["cases"]
    assert relevant["changed"] is True
    assert unrelated["changed"] is False

    inspected = c.get(
        f"/api/correction-transfer/{proposed['id']}",
        headers=headers(),
    ).json()
    assert [event["status"] for event in inspected["events"]] == ["proposed", "accepted"]

    undone = c.post(
        f"/api/correction-transfer/{proposed['id']}/undo",
        headers=headers(),
    )
    assert undone.json()["status"] == "undone"


def test_boundary_and_rejected_decision(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "helicon_home", lambda: str(tmp_path))
    c = client()
    assert c.get("/api/correction-transfer/example").status_code == 403
    assert c.get(
        "/api/correction-transfer/example",
        headers={"X-Helicon-Local": "1", "Host": "foreign.example"},
    ).status_code == 403

    example = c.get("/api/correction-transfer/example", headers=headers()).json()
    fields = {key: value for key, value in example.items() if key != "cases"}
    proposal = c.post("/api/correction-transfer/proposals", json=fields, headers=headers()).json()
    rejected = c.post(
        f"/api/correction-transfer/{proposal['id']}/decision",
        json={"decision": "reject"},
        headers=headers(),
    )
    assert rejected.json()["status"] == "rejected"
    comparison = c.post(
        "/api/correction-transfer/compare",
        json={"cases": example["cases"]},
        headers=headers(),
    ).json()
    assert all(not case["changed"] for case in comparison["cases"])
