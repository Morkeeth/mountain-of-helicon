"""glaze fix-skills / glaze.writeback: dry-run proposes without writing; --apply
writes the description into frontmatter with a .bak backup; files that already
have a description are never touched; a second run is a no-op; no Qwen key
degrades to a skip. The Qwen call is mocked throughout."""
import os

import pytest

from glaze import cli, writeback
from glaze.connectors.skills import _parse_frontmatter
from glaze.writeback import fix_skills, insert_description

DESC = "Trigger when the user asks to deploy; runs the deploy checklist."

MISSING = "---\nname: deployer\n---\n\n# Deployer\n\nRuns the deploy checklist step by step.\n"
HAS_DESC = "---\nname: reviewer\ndescription: Reviews diffs for bugs.\n---\n\n# Reviewer\n\nBody.\n"
EMPTY_DESC = "---\nname: empty\ndescription:\n---\n\n# Empty\n\nHas the key but no value.\n"
NO_FM = "# Bare skill\n\nNo frontmatter at all, just a body.\n"


class FakeClient:
    pass


@pytest.fixture
def skills_dir(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    for name, text in [("deployer", MISSING), ("reviewer", HAS_DESC),
                       ("empty", EMPTY_DESC), ("bare", NO_FM)]:
        d = root / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(text)
    monkeypatch.setattr(writeback, "complete",
                        lambda client, system, user, model="", operation="": DESC)
    return root


def _read(root, name):
    return (root / name / "SKILL.md").read_text()


def _actions(result):
    return {r["rel"]: r["action"] for r in result["records"]}


def test_dry_run_proposes_and_writes_nothing(skills_dir):
    result = fix_skills(str(skills_dir), client=FakeClient(), apply=False)
    actions = _actions(result)

    assert actions["reviewer/SKILL.md"] == "has_description"
    for rel in ("deployer/SKILL.md", "empty/SKILL.md", "bare/SKILL.md"):
        assert actions[rel] == "proposed"
    proposed = {r["rel"]: r.get("description") for r in result["records"]
                if r["action"] == "proposed"}
    assert all(d == DESC for d in proposed.values())

    # nothing written, no backups
    assert _read(skills_dir, "deployer") == MISSING
    assert _read(skills_dir, "empty") == EMPTY_DESC
    assert _read(skills_dir, "bare") == NO_FM
    assert not list(skills_dir.rglob("*.bak"))


def test_apply_writes_description_and_bak(skills_dir):
    result = fix_skills(str(skills_dir), client=FakeClient(), apply=True)
    actions = _actions(result)
    assert actions["deployer/SKILL.md"] == "fixed"
    assert actions["reviewer/SKILL.md"] == "has_description"

    # description landed in frontmatter, body preserved
    for name in ("deployer", "empty", "bare"):
        fm, body = _parse_frontmatter(_read(skills_dir, name))
        assert fm["description"] == DESC, name
    assert "Runs the deploy checklist step by step." in _read(skills_dir, "deployer")
    assert "No frontmatter at all" in _read(skills_dir, "bare")
    # empty `description:` line was filled in, not duplicated
    assert _read(skills_dir, "empty").count("description:") == 1

    # backups hold the originals; untouched file has no .bak
    assert (skills_dir / "deployer" / "SKILL.md.bak").read_text() == MISSING
    assert (skills_dir / "empty" / "SKILL.md.bak").read_text() == EMPTY_DESC
    assert not (skills_dir / "reviewer" / "SKILL.md.bak").exists()
    assert _read(skills_dir, "reviewer") == HAS_DESC


def test_second_apply_run_is_noop(skills_dir):
    fix_skills(str(skills_dir), client=FakeClient(), apply=True)
    snapshot = {p: p.read_text() for p in skills_dir.rglob("*") if p.is_file()}

    result = fix_skills(str(skills_dir), client=FakeClient(), apply=True)
    assert set(_actions(result).values()) == {"has_description"}
    assert {p: p.read_text() for p in skills_dir.rglob("*") if p.is_file()} == snapshot


def test_no_client_skips_without_writing(skills_dir):
    result = fix_skills(str(skills_dir), client=None, apply=True)
    actions = _actions(result)
    assert actions["deployer/SKILL.md"] == "skipped_no_client"
    assert actions["reviewer/SKILL.md"] == "has_description"
    assert _read(skills_dir, "deployer") == MISSING
    assert not list(skills_dir.rglob("*.bak"))


def test_insert_description_variants():
    with_fm = insert_description("---\nname: x\n---\nbody\n", "D.")
    fm, body = _parse_frontmatter(with_fm)
    assert fm == {"name": "x", "description": "D."} and body == "body\n"

    no_fm = insert_description("body only\n", "D.")
    fm, body = _parse_frontmatter(no_fm)
    assert fm == {"description": "D."} and "body only" in body


def test_cli_fix_skills_no_key(skills_dir, monkeypatch, capsys):
    from types import SimpleNamespace
    monkeypatch.setattr("glaze.config.load_config", lambda path=None: {})
    cli.cmd_fix_skills(SimpleNamespace(apply=False, skills_dir=str(skills_dir)))
    out = capsys.readouterr().out
    assert "no Qwen key" in out
    assert "deployer/SKILL.md" in out
    assert not list(skills_dir.rglob("*.bak"))


def test_cli_fix_skills_dry_run_prints_proposals(skills_dir, monkeypatch, capsys):
    from types import SimpleNamespace
    monkeypatch.setattr("glaze.config.load_config",
                        lambda path=None: {"qwen_api_key": "test"})
    monkeypatch.setattr("glaze.qwen.get_client", lambda config: FakeClient())
    cli.cmd_fix_skills(SimpleNamespace(apply=False, skills_dir=str(skills_dir)))
    out = capsys.readouterr().out
    assert "[would fix] deployer/SKILL.md" in out
    assert DESC in out
    assert "Dry-run: nothing written" in out
    assert _read(skills_dir, "deployer") == MISSING
