import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(home: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env.pop("HELICON_CONFIG", None)
    env.pop("QWEN_API_KEY", None)
    env.pop("DASHSCOPE_API_KEY", None)
    return subprocess.run(
        [sys.executable, "-m", "helicon", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def _new_user(home: Path) -> None:
    vault = home / "Documents" / "Obsidian"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "stale.md").write_text(
        "# Deployment\n\nRELAY is the current deployment service.\n"
    )

    memory = home / ".claude" / "memory"
    memory.mkdir(parents=True)
    (memory / "project.md").write_text(
        "# Project\n\nThe project was renamed from RELAY to FAVOUR. "
        "FAVOUR is current.\n"
    )

    repo = home / "CODE" / "sample-app"
    (repo / "src").mkdir(parents=True)
    (repo / "CLAUDE.md").write_text(
        "# Rules\n\nThe entry point is `src/main.py`.\n"
    )
    (repo / "src" / "main.py").write_text('print("FAVOUR")\n')
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=new@example.com", "-c", "user.name=New User",
         "commit", "-qm", "init"],
        cwd=repo,
        check=True,
    )


def test_new_user_vault_setup_reaches_a_visible_ruling(tmp_path):
    home = tmp_path / "home"
    _new_user(home)

    initialized = _run(home, "init", "--force")
    config_path = home / ".helicon" / "config.json"
    assert config_path.is_file()
    assert "Wrote " + str(config_path) in initialized.stdout
    config = json.loads(config_path.read_text())
    assert set(config["connectors"]) == {"claude-code", "obsidian", "git"}
    assert config["db_path"] == str(home / ".helicon" / "helicon.db")
    assert not (ROOT / "config.json").exists()

    scanned = _run(home, "scan")
    assert "claude-code: 1" in scanned.stdout
    assert "obsidian: 1" in scanned.stdout
    assert "git: 1" in scanned.stdout

    with sqlite3.connect(config["db_path"]) as conn:
        by_source = dict(conn.execute(
            "SELECT source, COUNT(*) FROM helicon_cubes GROUP BY source"
        ).fetchall())
    assert by_source == {"claude-code": 1, "git": 1, "obsidian": 1}

    doctor = _run(home, "doctor")
    assert doctor.returncode == 0
    assert "[WARN] semantic — no embeddings stored" in doctor.stdout
    assert "check(s) failed" not in doctor.stdout

    _run(home, "alias", "--add", "RELAY", "FAVOUR",
         "--renamed-at", "2000-01-01")
    filed = _run(home, "alias", "--scan")
    assert "filed: Dead name 'RELAY'" in filed.stdout

    queue = _run(home, "resolve", "--list")
    assert "Open findings: 1" in queue.stdout
    assert "R4 supersession / rename" in queue.stdout
    assert "Dead name 'RELAY'" in queue.stdout


def test_empty_home_init_creates_an_editable_config_instead_of_looping(tmp_path):
    home = tmp_path / "empty-home"
    home.mkdir()

    initialized = _run(home, "init")

    config_path = home / ".helicon" / "config.json"
    assert config_path.is_file()
    config = json.loads(config_path.read_text())
    assert config["connectors"] == {}
    assert "A user config will still be created" in initialized.stdout
    assert "edit " + str(config_path) in initialized.stdout
    assert "run `helicon init`" not in initialized.stdout

    scanned = _run(home, "scan")
    assert "Edit " + str(config_path) in scanned.stdout
    assert "helicon demo" in scanned.stdout
    assert "helicon init" not in scanned.stdout


def test_missing_explicit_config_points_to_working_demo_command(tmp_path):
    home = tmp_path / "empty-home"
    home.mkdir()
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["HELICON_CONFIG"] = str(home / "missing.json")

    result = subprocess.run(
        [sys.executable, "-m", "helicon", "scan"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    message = result.stdout + result.stderr
    assert "helicon demo" in message
    assert "scripts/demo_seed.py" not in message
    assert "config-demo.json" not in message
