"""Golden first-run + security defaults.

The judge's whole experience is `helicon demo` -> a populated, safe, local
dashboard. These pin the properties that make that true: the store is seeded
(not an empty warehouse), the demo touches no personal source and no network,
and the server never binds to the world by default.
"""
import json

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
