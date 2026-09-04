import json
import pytest

from helicon.setup_audit import audit_setup
from helicon.setupcheck import axis2


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_bash_handler_without_bash_route_is_visible_and_read_only(tmp_path):
    hook = write(tmp_path / ".claude/hooks/policy.sh", 'elif tool == "Bash":\n    pass\n')
    settings = write(tmp_path / ".claude/settings.json", json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Write|Edit", "hooks": [{"command": str(hook)}]}
    ]}, "env": {"SECRET": "canary-must-not-leave-config"}}))
    before = settings.read_bytes()
    report = audit_setup(tmp_path, tmp_path)
    assert any(f["id"].startswith("hook-bash-route:") for f in report["findings"])
    assert "canary-must-not-leave-config" not in json.dumps(report)
    assert settings.read_bytes() == before
    settings.write_text(settings.read_text().replace("Write|Edit", "Write|Edit|Bash"))
    assert not any(f["id"].startswith("hook-bash-route:") for f in audit_setup(tmp_path, tmp_path)["findings"])


def test_three_harnesses_and_nested_skills_are_discovery_not_delivery(tmp_path):
    write(tmp_path / ".codex/AGENTS.md", "old instructions")
    override = write(tmp_path / ".codex/AGENTS.override.md", "override")
    write(tmp_path / ".claude/rules/style.md", "writing")
    write(tmp_path / ".cursor/rules/style.mdc", "alwaysApply: true")
    write(tmp_path / ".codex/skills/.system/example/SKILL.md", "skill")
    (tmp_path / ".claude/skills/not-a-skill").mkdir(parents=True)
    r = audit_setup(tmp_path, tmp_path)
    paths = [f["path"] for f in r["files"]]
    assert str(override) in paths
    assert str(tmp_path / ".codex/AGENTS.md") not in paths
    assert len(r["skills"]) == 1
    assert {f["harness"] for f in r["findings"] if f["status"] == "unmeasured"} == {"claude", "codex", "cursor"}


def test_malformed_settings_does_not_report_clean(tmp_path):
    write(tmp_path / ".claude/settings.json", "{")
    r = audit_setup(tmp_path, tmp_path)
    assert any(f["id"] == "claude-settings" and f["status"] == "unmeasured" for f in r["findings"])


@pytest.mark.parametrize("matcher", ["", "*", "Bash", "ash"])
def test_catch_all_and_regex_routes_do_not_raise_false_alarms(tmp_path, matcher):
    hook = write(tmp_path / ".claude/hooks/policy.sh", 'if tool == "Bash": pass')
    write(tmp_path / ".claude/settings.json", json.dumps({"hooks": {"PreToolUse": [
        {"matcher": matcher, "hooks": [{"command": str(hook)}]}
    ]}}))
    assert not any(f["id"].startswith("hook-") for f in audit_setup(tmp_path, tmp_path)["findings"])


def test_compaction_does_not_silently_restore_a_dead_pointer(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    write(tmp_path / ".helicon/config.json", json.dumps({"connectors": {"obsidian": {
        "enabled": True, "vault_path": str(vault)}}}))
    reminder = write(tmp_path / ".claude/hooks/reminder.txt", "Dashboard: 00 Dashboard/old.md (read first)")
    write(tmp_path / ".claude/settings.json", json.dumps({"hooks": {"PostCompact": [
        {"hooks": [{"command": f"cat {reminder} 2>/dev/null || echo ''"}]}
    ]}}))
    assert any(f["id"].startswith("compact-reference:") for f in audit_setup(tmp_path, tmp_path)["findings"])
    write(vault / "00 Dashboard/old.md", "exists")
    assert not any(f["id"].startswith("compact-reference:") for f in audit_setup(tmp_path, tmp_path)["findings"])


def test_two_files_cannot_pass_effective_context_budget():
    cen = {"context_files": [{"label": "global CLAUDE.md", "exists": True, "lines": 1, "bytes": 10}], "memories": {}}
    chip = next(c for c in axis2(None, cen, {}) if c["id"] == "context-weight")
    assert chip["verdict"] == "UNMEASURED"
