"""Rules and hooks are held as cubes, so ask can say which rule a hook enforces."""
import json
import sqlite3

import pytest


@pytest.fixture
def agent_home(tmp_path):
    home = tmp_path / "agent-home"
    (home / "rules").mkdir(parents=True)
    (home / "hooks").mkdir()
    (home / "rules" / "WRITE.md").write_text(
        "---\ntype: rule\ndescription: The checks that run before a prose file is written. "
        "Enforced by hooks/write-rules.sh, not by memory.\npaths:\n  - \"**/*.md\"\n---\n\n"
        "# WRITE RULES\n\n1. No long dashes.\n", encoding="utf-8")
    (home / "rules" / "EVIDENCE.md").write_text(
        "# EVIDENCE\n\n1. **Probe the object, not the document about the object.**\n", encoding="utf-8")
    (home / "rules" / "LUNCH.md").write_text(
        "# LUNCH\n\nEat at noon. Checked by hooks/lunch-bell.sh and hooks/gone.sh.\n", encoding="utf-8")
    (home / "hooks" / "write-rules.sh").write_text(
        "#!/usr/bin/env bash\n# WRITE RULES: checks the hard bans before any file is written.\n"
        "# Exit 2 blocks the call.\nset -uo pipefail\nrm -rf /should/never/run\n", encoding="utf-8")
    (home / "hooks" / "check-secrets.sh").write_text(
        "#!/usr/bin/env bash\n# check-secrets: gate on shell commands that print a key.\nexit 0\n", encoding="utf-8")
    (home / "hooks" / "lunch-bell.sh").write_text("#!/bin/sh\n# Rings at noon.\n", encoding="utf-8")
    (home / "hooks" / "write-rules.sh.bak-2026").write_text("old copy\n", encoding="utf-8")
    (home / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Write|Edit", "hooks": [{"type": "command", "command": str(home / "hooks" / "write-rules.sh")}]},
        {"matcher": "Bash", "hooks": [{"type": "command", "command": str(home / "hooks" / "check-secrets.sh")}]},
    ]}}), encoding="utf-8")
    return home


def _by_ref(results):
    return {r.source_ref: r for r in results}


def test_off_until_a_home_is_named(agent_home):
    from helicon.connectors import CONNECTORS, setup_rules

    assert CONNECTORS["setup-rules"] is setup_rules.scan
    assert setup_rules.scan({}) == []


def test_each_rule_and_hook_is_a_cube_with_its_enforcement(agent_home):
    from helicon.connectors import setup_rules

    cubes = _by_ref(setup_rules.scan({"claude_home": str(agent_home)}))
    write = cubes["rules/WRITE.md"]
    assert write.metadata["hook_enforced"] is True
    assert write.metadata["enforced_by_hook"] == [str(agent_home / "hooks" / "write-rules.sh")]
    assert "PreToolUse on Write|Edit" in write.content
    assert write.metadata["says"].startswith("The checks that run before a prose file is written")
    assert write.metadata["file_path"] == str(agent_home / "rules" / "WRITE.md")
    assert write.metadata["loaded"] == "only for matching paths"

    evidence = cubes["rules/EVIDENCE.md"]
    assert evidence.metadata["hook_enforced"] is False and evidence.metadata["enforced_by_hook"] == []
    assert "Probe the object" in evidence.metadata["says"]

    hook = cubes["hooks/write-rules.sh"]
    assert hook.metadata["enforces_rule"] == ["WRITE.md"]
    assert hook.metadata["does"].startswith("WRITE RULES: checks the hard bans")
    assert "rm -rf" not in hook.content  # the header is read, the code is not
    assert cubes["hooks/check-secrets.sh"].metadata["runs_on"] == ["PreToolUse on Bash"]
    assert "hooks/write-rules.sh.bak-2026" not in cubes


def test_a_rule_that_names_an_unwired_or_missing_hook_is_not_enforced(agent_home):
    from helicon.connectors import setup_rules

    lunch = _by_ref(setup_rules.scan({"claude_home": str(agent_home)}))["rules/LUNCH.md"]
    assert lunch.metadata["hook_enforced"] is False
    claims = " ".join(lunch.metadata["unenforced_hook_claims"])
    assert "lunch-bell.sh (file is there, settings.json does not wire it)" in claims
    assert "gone.sh (no such file)" in claims


def test_ask_names_the_rule_a_hook_enforces(agent_home, tmp_path, monkeypatch):
    from helicon.connectors import scan_all
    from helicon.db import init_db, insert_cube
    from helicon.retrieve_guard import format_guarded_context, guarded_context
    from helicon.scanner import result_to_cube

    monkeypatch.setenv("HELICON_RULINGS_FILE", "")
    db = str(tmp_path / "store.db")
    init_db(db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    off = {name: {"enabled": False} for name in
           ("claude-code", "obsidian", "git", "chatgpt", "cursor", "cursor-cloud", "codex", "agent-rules")}
    for result in scan_all({"connectors": {**off, "setup-rules": {"claude_home": str(agent_home)}}}):
        insert_cube(conn, result_to_cube(result))
    conn.commit()

    res = guarded_context(conn, "which rules are enforced by a hook")
    hits = [m for m in res["safe_context"] if "WRITE.md" in m["title"]]
    assert hits and any("write-rules.sh" in m["title"] + m["content_preview"] for m in hits)
    enforced_titles = [m["title"] for m in res["safe_context"] if "enforced by hook" in m["title"]]
    assert enforced_titles and all("EVIDENCE.md" not in t and "LUNCH.md" not in t for t in enforced_titles)
    text = format_guarded_context(res)
    assert "WRITE.md" in text and "write-rules.sh" in text


def test_a_question_that_quotes_a_sentence_deep_in_a_rule_finds_the_rule(tmp_path, agent_home, monkeypatch):
    """Keyword-only store: the rule cube must hold the rule's own sentences, not only its description."""
    from helicon.connectors import setup_rules
    from helicon.db import init_db, insert_cube
    from helicon.mcp_server import handle_tool_call
    from helicon.models import ConnectorResult
    from helicon.scanner import result_to_cube

    (agent_home / "rules" / "KITES.md").write_text(
        "---\ndescription: How the stall is run.\n---\n\n# KITES\n\n"
        + "".join(f"{n}. Filler line number {n} about the till and the awning.\n" for n in range(1, 30))
        + "30. **Never fly a `box_kite` near the harbour crane.**\n", encoding="utf-8")
    monkeypatch.setenv("HELICON_RULINGS_FILE", "")
    db = str(tmp_path / "store.db")
    init_db(db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    found = setup_rules.scan({"claude_home": str(agent_home)})
    noise = [ConnectorResult(source="obsidian", source_ref=f"n{n}.md", type="project", title=f"Harbour note {n}",
                             content=f"The harbour crane lifts crates at berth {n}. A kite was seen once.",
                             created_at="2026-10-01T00:00:00") for n in range(30)]
    for result in found + noise:
        insert_cube(conn, result_to_cube(result))
    conn.commit()

    parts = [r for r in found if r.source_ref.startswith("rules/KITES.md")]
    assert len(parts) >= 2, "a rule longer than one cube continues in part cubes"
    assert all(len(r.content) <= setup_rules.RULE_TEXT_CHARS + 400 for r in parts)
    deep = next(r for r in parts if "harbour crane" in r.content)
    assert "KITES.md" in deep.title and "box_kite" in deep.content and "**" not in deep.content

    answer = json.loads(handle_tool_call(
        "helicon_ask", {"question": "Which rule says never fly a box_kite near the harbour crane?", "limit": 10}, conn))
    assert any("KITES.md" in m["title"] for m in answer["safe_context"])
    # A short rule stays one cube and now holds its sentence.
    evidence = next(r for r in found if r.source_ref == "rules/EVIDENCE.md")
    assert "Probe the object, not the document about the object." in evidence.content
