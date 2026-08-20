"""Hackathon ADK local witness path."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parents[1]
ADK = REPO / "hackathon" / "adk"


def _load_agent_module():
    agent_dir = str(ADK / "agent")
    if agent_dir not in sys.path:
        sys.path.insert(0, agent_dir)
    spec = importlib.util.spec_from_file_location("adk_main", ADK / "agent" / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_seed_demo_db_produces_measurable_wedge(tmp_path):
    db = tmp_path / "demo.db"
    sys.path.insert(0, str(REPO))
    import importlib.util
    mod_spec = importlib.util.spec_from_file_location("seed_demo_db", ADK / "seed_demo_db.py")
    mod = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(mod)
    out = mod.seed(str(db))
    assert out["total_cubes"] == 15_001
    assert db.is_file()


def test_run_local_json_witness(tmp_path):
    db = tmp_path / "demo.db"
    sys.path.insert(0, str(REPO))
    import importlib.util
    mod_spec = importlib.util.spec_from_file_location(
        "seed_demo_db", ADK / "seed_demo_db.py")
    mod = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(mod)
    mod.seed(str(db))

    out_path = tmp_path / "run.json"
    proc = subprocess.run(
        [sys.executable, str(ADK / "run_local.py"), "--db", str(db), "-o", str(out_path)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out_path.read_text())
    assert payload["science"]["unmeasurable_count"] >= 1
    assert any(v["verdict"] == "UNMEASURABLE" for v in payload["science"]["verdicts"])
    assert payload["store_truth"]["findings"]
    assert len(payload["measure"]["weeks"]) >= 1


def test_agent_run_subprocess_witness(tmp_path):
    db = tmp_path / "demo.db"
    sys.path.insert(0, str(REPO))
    mod_spec = importlib.util.spec_from_file_location(
        "seed_demo_db", ADK / "seed_demo_db.py")
    mod = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(mod)
    mod.seed(str(db))

    agent = _load_agent_module()
    agent.DEFAULT_DB = db
    agent.REPO = REPO

    from fastapi.testclient import TestClient

    client = TestClient(agent.app)
    with patch.object(agent, "write_run") as mock_write:
        resp = client.post("/run", headers={"X-Trigger": "manual"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["science"]["unmeasurable_count"] >= 1
    assert body["run_id"]
    mock_write.assert_called_once()
    doc = mock_write.call_args[0][1]
    assert doc["trigger"] == "manual"
    assert doc["science"]["unmeasurable_count"] >= 1


def test_measurement_bench_db_flag_needs_no_user_config(tmp_path, monkeypatch):
    """Cloud/demo path: --db alone must not require ~/.helicon/config.json."""
    db = tmp_path / "demo.db"
    sys.path.insert(0, str(REPO))
    mod_spec = importlib.util.spec_from_file_location(
        "seed_demo_db", ADK / "seed_demo_db.py")
    mod = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(mod)
    mod.seed(str(db))

    home = tmp_path / "empty-home"
    home.mkdir()
    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()
                  if k not in ("HELICON_CONFIG", "HELICON_HOME")}),
        "HOME": str(home),
        "HELICON_HOME": str(home / ".helicon"),
    }
    env.pop("HELICON_CONFIG", None)
    proc = subprocess.run(
        [sys.executable, "-m", "helicon", "measurement-bench",
         "--json", "--db", str(db)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "No config at" not in proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["science"]["unmeasurable_count"] >= 1


def test_brief_api_local_run_json(tmp_path, monkeypatch):
    run_path = tmp_path / "run.json"
    payload = {
        "repro_command": "helicon measurement-bench --json",
        "recorded_at": "2026-08-20T00:00:00",
        "science": {
            "unmeasurable_count": 1,
            "verdicts": [{"id": "memory-accuracy-10k", "verdict": "UNMEASURABLE", "claim": "test"}],
        },
    }
    run_path.write_text(json.dumps(payload))

    spec = importlib.util.spec_from_file_location("brief_serve", ADK / "brief" / "serve.py")
    brief = importlib.util.module_from_spec(spec)
    monkeypatch.setenv("LOCAL_RUN_JSON", str(run_path))
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    spec.loader.exec_module(brief)

    from fastapi.testclient import TestClient

    client = TestClient(brief.app)
    resp = client.get("/api/run")
    assert resp.status_code == 200
    assert resp.json()["science"]["unmeasurable_count"] == 1

