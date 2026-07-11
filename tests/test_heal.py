"""Tests for the self-healing audit loop (helicon.heal) + the --apply safety guard.

The demo store is deterministic — scripts.demo_seed plants three universally
legible drifts, one per movable gate (consistency / freshness / volatility) — so
heal() is fully testable without touching the real vault. Covers the money-path
that was previously untested: --apply retires (kills) cubes, so a dry run must
move nothing and the guard must refuse --apply on the real store.
"""
import os
import sys
from types import SimpleNamespace

# tests/ lives under the repo root; make `scripts` importable like the CLI does.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helicon.db import init_db
from helicon.heal import heal
import scripts.demo_seed as demo_seed


def _seeded(tmp_path):
    db = str(tmp_path / "heal-demo.db")
    demo_seed.seed(db)
    return init_db(db)


def _active(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE review_status != 'killed'"
    ).fetchone()[0]


def test_demo_dryrun_finds_drift_but_kills_nothing(tmp_path):
    conn = _seeded(tmp_path)
    before = _active(conn)
    env = heal(conn, apply=False, store_label="demo")

    assert env["summary"]["findings"] >= 1, "demo store should surface drift"
    assert env["summary"]["applied"] == 0
    assert "after" not in env["gate_scores"], "dry run must not re-score"
    assert _active(conn) == before, "dry run must not retire any cube"


def test_demo_apply_moves_gates_and_retires(tmp_path):
    conn = _seeded(tmp_path)
    env = heal(conn, apply=True, store_label="demo")

    assert env["summary"]["applied"] >= 1
    assert "after" in env["gate_scores"]
    assert "gate_delta" in env
    assert any(d > 0 for d in env["gate_delta"].values()), \
        "applying repairs should move at least one gate up"

    killed = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE review_status = 'killed'"
    ).fetchone()[0]
    assert killed >= 1, "accepted repairs must actually retire cubes"


def test_apply_guard_refuses_real_store(monkeypatch, capsys):
    """cmd_heal must refuse --apply on the REAL store without --yes-really.
    We make the real config load explode; if the guard holds it is never reached."""
    import helicon.config as config_mod

    def _boom():
        raise AssertionError("guard failed: cmd_heal reached the real store load")

    monkeypatch.setattr(config_mod, "load_config", _boom)

    from helicon.cli import cmd_heal
    args = SimpleNamespace(demo=False, apply=True, yes_really=False,
                           reset=False, json=False)
    cmd_heal(args)  # must return early, not raise

    out = capsys.readouterr().out.lower()
    assert "refusing" in out


def test_apply_guard_allows_demo(tmp_path, monkeypatch):
    """The guard must NOT interfere with the safe demo path."""
    import helicon.config as config_mod

    def _boom():
        raise AssertionError("demo path should not touch real config")

    monkeypatch.setattr(config_mod, "load_config", _boom)

    from helicon.cli import cmd_heal
    # point the demo seed/db at a temp location via monkeypatching is overkill;
    # demo uses its own helicon-demo.db and never calls load_config — that's the
    # assertion. reset=True keeps it deterministic.
    args = SimpleNamespace(demo=True, apply=True, yes_really=False,
                           reset=True, json=True)
    cmd_heal(args)  # demo + apply is always allowed; must not raise
