"""Golden first-run + security defaults.

The judge's whole experience is `helicon demo` -> a populated, safe, local
dashboard. These pin the properties that make that true: the store is seeded
(not an empty warehouse), the demo touches no personal source and no network,
and the server never binds to the world by default.
"""
import json
from pathlib import Path

import pytest

import helicon.demo as demo
import helicon.cli as cli


def test_demo_seeds_a_populated_store_with_a_ruling_queue(tmp_path):
    db = str(tmp_path / "demo.db")
    res = demo.seed(db)
    assert res["cubes"] > 0, "empty demo store = the empty-warehouse first run we are fixing"
    from helicon.db import init_db
    conn = init_db(db)
    assert conn.execute("SELECT COUNT(*) FROM helicon_cubes").fetchone()[0] > 0
    # findings are pre-filed so the review queue is not empty on first open
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] > 0


def test_demo_config_is_keyless_local_and_scans_nothing(tmp_path):
    path, _ = demo.write_demo_config(str(tmp_path / "config-demo.json"))
    cfg = json.load(open(path))
    assert cfg["server"]["host"] == "127.0.0.1"   # never exposes a mutation API to the network
    assert cfg["qwen_api_key"] == ""              # keyless: the deterministic exam is the demo
    assert cfg["connectors"] == {}                # scans no personal source


def test_demo_defaults_to_user_writable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HELICON_DEMO_DIR", str(tmp_path / "demo-home"))

    info = demo.ensure_demo()

    assert info["db"] == str(tmp_path / "demo-home" / "helicon-demo.db")
    assert info["config"] == str(tmp_path / "demo-home" / "config-demo.json")
    assert Path(info["db"]).is_file()
    assert json.loads(Path(info["config"]).read_text())["db_path"] == info["db"]
    assert "site-packages" not in info["db"]


def test_config_environment_is_read_when_demo_sets_it(tmp_path, monkeypatch):
    from helicon.config import load_config

    config_path = tmp_path / "late-config.json"
    config_path.write_text(json.dumps({"db_path": str(tmp_path / "late.db")}))
    monkeypatch.setenv("HELICON_CONFIG", str(config_path))

    assert load_config()["db_path"] == str(tmp_path / "late.db")


def test_demo_builds_missing_dashboard_once(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    web = repo / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text("{}")
    fake_cli = repo / "helicon" / "cli.py"
    fake_cli.parent.mkdir()
    fake_cli.write_text("")
    monkeypatch.setattr(cli, "__file__", str(fake_cli))
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/npm")
    calls = []

    def fake_run(command, cwd, check):
        calls.append(command)
        if command[-1] == "build":
            (web / "dist").mkdir()
            (web / "dist" / "index.html").write_text("<html></html>")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert cli._ensure_demo_dashboard() == str(web / "dist" / "index.html")
    assert calls == [["/usr/bin/npm", "ci"], ["/usr/bin/npm", "run", "build"]]
    calls.clear()
    assert cli._ensure_demo_dashboard() == str(web / "dist" / "index.html")
    assert calls == []


def test_demo_without_source_or_npm_exits_clearly(tmp_path, monkeypatch):
    """A SOURCE TREE with scripts/demo.sh but no built dashboard is still told
    about the terminal demo, because that exit actually exists here.

    The original fixture had no scripts/ either, which made it indistinguishable
    from a wheel install — and the assertion quietly encoded "there is always a
    checkout". uvx made that false: see tests/test_demo_without_a_checkout.py.
    The message now discriminates on what is ON DISK rather than inferring.
    """
    fake_cli = tmp_path / "repo" / "helicon" / "cli.py"
    fake_cli.parent.mkdir(parents=True)
    fake_cli.write_text("")
    (tmp_path / "repo" / "scripts").mkdir()
    (tmp_path / "repo" / "scripts" / "demo.sh").write_text("#!/bin/bash\n")
    monkeypatch.setattr(cli, "__file__", str(fake_cli))
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    with pytest.raises(SystemExit, match="demo.sh"):
        cli._ensure_demo_dashboard()


def test_serve_binds_loopback_by_default(monkeypatch):
    monkeypatch.setattr("helicon.config.load_config", lambda: {})
    assert cli._serve_host() == "127.0.0.1", "serve must not face the network by default"
    assert cli._serve_host("0.0.0.0") == "0.0.0.0", "explicit override is still honored"


def test_skill_findings_do_not_scan_a_real_dir_without_the_connector(monkeypatch):
    """The review queue used to scan a hardcoded ~/.claude/skills every request,
    leaking the host's real skills into a keyless demo. Off connector -> nothing."""
    import helicon.api.app as app_mod  # initialize the app fully first
    from helicon.api import findings
    monkeypatch.setattr(app_mod, "get_config", lambda: {"connectors": {}})
    assert findings._skill_findings("2026-07-19T00:00:00") == []
