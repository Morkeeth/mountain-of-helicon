"""Hackathon ADK local witness path."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ADK = REPO / "hackathon" / "adk"


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
