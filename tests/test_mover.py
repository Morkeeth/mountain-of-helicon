"""Slice 5: the context-mover.

Hermetic: the Qwen contradiction pass is opt-in and behind the CLI; here we test
the pure read/verify/plan/render so the honesty rule holds - memory does not
move if it is stale/volatile, and the target format renders correctly.
"""
from datetime import datetime

from helicon.mover import read_items, verify_item, plan_move, render, move


NOW = datetime(2026, 7, 14)


def test_verify_holds_volatile_and_stale():
    assert verify_item("FAVOUR is live with real money.", now=NOW)[0] is True
    assert verify_item("TODO: wire the points sink.", now=NOW)[0] is False        # volatile
    assert verify_item("Deploy is currently blocked on KYC.", now=NOW)[0] is False  # volatile
    ok, why = verify_item("Security audit done 2026-05-01.", now=NOW)             # 74d old
    assert ok is False and "stale date" in why
    assert verify_item("Audit done 2026-07-10.", now=NOW)[0] is True             # 4d, fresh


def test_plan_move_splits_kept_and_held():
    items = [{"text": "Ledger is a hardware wallet.", "source": "a"},
             {"text": "TODO: fix the thing.", "source": "a"},
             {"text": "Meeting 2026-01-01.", "source": "a"}]
    plan = plan_move(items, now=NOW)
    assert [i["text"] for i in plan["kept"]] == ["Ledger is a hardware wallet."]
    assert len(plan["held"]) == 2
    assert all("reason" in h for h in plan["held"])


def test_render_targets():
    items = [{"text": "one"}, {"text": "two"}]
    assert render(items, "cursor") == "- one\n- two\n"
    assert "moved + verified by Mount Helicon" in render(items, "claude-code")
    assert render(items, "markdown").startswith("# Moved memory")


def test_read_items_bullets(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_text("# Rules\n\n- Always verify output.\n- Never fake data.\n\nSome prose.\n")
    items = read_items(str(p))
    assert [i["text"] for i in items] == ["Always verify output.", "Never fake data."]


def test_move_dry_run_does_not_write(tmp_path):
    src = tmp_path / "src.md"
    src.write_text("- Ledger is a hardware wallet.\n- TODO: later.\n")
    out = tmp_path / "CLAUDE.md"
    res = move(str(src), "claude-code", out_path=str(out), apply=False, now=NOW)
    assert res["applied"] is False
    assert not out.exists()                      # dry-run never writes
    assert len(res["kept"]) == 1 and len(res["held"]) == 1


def test_move_apply_writes_with_backup(tmp_path):
    src = tmp_path / "src.md"
    src.write_text("- Ledger is a hardware wallet.\n")
    out = tmp_path / "CLAUDE.md"
    out.write_text("old content\n")
    res = move(str(src), "cursor", out_path=str(out), apply=True, now=NOW)
    assert res["applied"] is True
    assert out.read_text() == "- Ledger is a hardware wallet.\n"
    assert (tmp_path / "CLAUDE.md.bak").read_text() == "old content\n"   # backed up
