from fastapi import FastAPI
from fastapi.testclient import TestClient
from helicon.api import context_review as api


def client():
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    return TestClient(app, base_url="http://127.0.0.1:8420")


def test_local_boundary_rejects_foreign_origins_and_rebinding(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "get_config", lambda: {"context_review": {"projects": [{"id": "sample", "path": str(tmp_path)}]}})
    c = client()
    url = "/api/context-review/projects"
    assert c.get(url).status_code == 403
    assert c.get(url, headers={"X-Helicon-Local": "1", "Origin": "https://foreign.example"}).status_code == 403
    assert c.get(url, headers={"X-Helicon-Local": "1", "Host": "foreign.example"}).status_code == 403
    response = c.get(url, headers={"X-Helicon-Local": "1", "Origin": "http://127.0.0.1:8420"})
    assert response.status_code == 200
    assert response.json()["projects"][0]["path"] == str(tmp_path)


def test_broad_and_duplicate_roots_fail_closed(monkeypatch):
    monkeypatch.setattr(api, "get_config", lambda: {"context_review": {"projects": [{"id": "root", "path": "/"}]}})
    assert client().get("/api/context-review/projects", headers={"X-Helicon-Local": "1"}).status_code == 503


def fixture_project(monkeypatch, tmp_path):
    project, home, state = tmp_path / "project", tmp_path / "home", tmp_path / "state"
    project.mkdir(); home.mkdir()
    (project / ".git").mkdir()
    source = project / "AGENTS.md"
    source.write_text("Atlas phase = Build\nAtlas phase = Validate\nBirch phase = Validate\n")
    monkeypatch.setattr(api, "get_config", lambda: {"context_review": {"home": str(home), "projects": [{"id": "test", "path": str(project)}]}})
    monkeypatch.setattr(api, "helicon_home", lambda: str(state))
    return source, state


def test_actual_review_save_preview_apply_history_and_undo(monkeypatch, tmp_path):
    source, state = fixture_project(monkeypatch, tmp_path)
    c = client()
    headers = {"X-Helicon-Local": "1"}
    def post(action, **fields):
        result = c.post("/api/context-review/" + action, json={"project_id": "test", **fields}, headers=headers)
        assert result.status_code == 200, result.text
        return result.json()
    original = source.read_bytes()
    read = post("read")
    assert not state.exists(), "Reading must not create run state"
    assert c.get("/api/context-review/history?project_id=test", headers=headers).json() == {"snapshots": [], "corrections": []}
    assert not state.exists(), "Empty history must not create run state"
    saved = post("snapshots", revision=read["revision"])
    finding = next(f for f in read["report"]["findings"] if f["kind"] == "source-disagreement")
    index = next(i for i,e in enumerate(finding["evidence"]) if "phase = Build" in e["quote"])
    preview = post("preview", snapshot_id=saved["id"], finding_id=finding["id"], evidence_index=index,
                   replacement="Atlas phase = Validate\n", reason="Controlled fixture: align the current phase")
    assert source.read_bytes() == original
    applied = post("apply", preview_id=preview["id"], preview_hash=preview["hash"])
    assert source.read_text() == "Atlas phase = Validate\nAtlas phase = Validate\nBirch phase = Validate\n"
    comparison = post("compare", baseline_id=saved["id"])
    assert next(g for g in comparison["groups"] if g["label"] == "Resolved by the checks run")["items"]
    history = c.get("/api/context-review/history?project_id=test", headers=headers).json()
    assert len(history["snapshots"]) == 1
    assert history["corrections"][0]["status"] == "applied"
    post("undo", correction_id=applied["correction_id"])
    assert source.read_bytes() == original


def test_changed_source_cannot_be_saved_or_applied(monkeypatch, tmp_path):
    source, _ = fixture_project(monkeypatch, tmp_path)
    c = client(); headers = {"X-Helicon-Local": "1"}
    read = c.post("/api/context-review/read", json={"project_id": "test"}, headers=headers).json()
    source.write_text(source.read_text() + "A later human edit.\n")
    result = c.post("/api/context-review/snapshots", json={"project_id": "test", "revision": read["revision"]}, headers=headers)
    assert result.status_code == 409
    assert "later human edit" in source.read_text()
