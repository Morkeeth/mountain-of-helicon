"""helicon doorway install — the stranger's one-command gate.

Writing to ~/.claude/settings.json is the single most dangerous thing in this
repo, so the writer is pinned hard: it must add exactly one group, disturb no
existing hook or key, be idempotent, and reverse itself exactly. The gate itself
is proven keyless and config-free (a temp git repo, a temp HELICON_HOME, no
config.json). Nothing here touches the network or the real home directory.
"""
import json
import os
import subprocess

import pytest

from helicon import doorway


def _settings(tmp_path, obj):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(obj, indent=2))
    return str(p)


def _git_repo(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "commit", "-qm", "fx"]):
        subprocess.run(cmd, cwd=root, env=env, check=True, capture_output=True)
    return str(root)


# --------------------------------------------------------------------------
# the settings writer — pure dict transforms
# --------------------------------------------------------------------------

def test_add_is_idempotent_and_never_double_writes():
    cmd = "py -m helicon doorway gate"
    once = doorway.add_doorway_hook({}, cmd)
    twice = doorway.add_doorway_hook(once, cmd)
    assert doorway.has_doorway_hook(once)
    assert once == twice
    assert len(once["hooks"]["UserPromptSubmit"]) == 1


def test_add_preserves_existing_hooks_and_keys():
    existing = {"hooks": {"UserPromptSubmit": [
        {"hooks": [{"type": "command", "command": "echo keep-me"}]}]},
        "model": "opus", "env": {"FOO": "1"}}
    new = doorway.add_doorway_hook(existing, "py -m helicon doorway gate")
    ups = new["hooks"]["UserPromptSubmit"]
    assert len(ups) == 2
    assert ups[0]["hooks"][0]["command"] == "echo keep-me"   # untouched, first
    assert new["model"] == "opus" and new["env"] == {"FOO": "1"}


def test_remove_is_exact_and_keeps_other_hooks():
    base = {"hooks": {"UserPromptSubmit": [
        {"hooks": [{"type": "command", "command": "echo keep-me"}]}]},
        "otherKey": 42}
    installed = doorway.add_doorway_hook(base, "py -m helicon doorway gate")
    removed = doorway.remove_doorway_hook(installed)
    assert removed == base                       # byte-for-byte round trip
    assert doorway.has_doorway_hook(removed) is False


def test_remove_prunes_empty_containers_it_created():
    installed = doorway.add_doorway_hook({}, "py -m helicon doorway gate")
    removed = doorway.remove_doorway_hook(installed)
    assert removed == {}                         # nothing we did not create survives


def test_remove_on_a_repo_without_our_hook_is_a_noop():
    base = {"hooks": {"SessionStart": [{"hooks": [{"type": "command",
                                                   "command": "x"}]}]}}
    assert doorway.remove_doorway_hook(base) == base


def test_gate_command_pins_this_interpreter():
    import sys
    assert doorway.gate_command() == f"{sys.executable} -m helicon doorway gate"


# --------------------------------------------------------------------------
# the file layer — load / backup / atomic write
# --------------------------------------------------------------------------

def test_load_settings_absent_or_empty_is_empty(tmp_path):
    assert doorway.load_settings(str(tmp_path / "nope.json")) == {}
    p = tmp_path / "empty.json"
    p.write_text("   \n")
    assert doorway.load_settings(str(p)) == {}


def test_malformed_settings_raises_rather_than_clobbers(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{ this is not json ")
    with pytest.raises(ValueError):
        doorway.load_settings(str(p))


def test_write_is_atomic_and_backup_copies_the_prior_file(tmp_path):
    path = _settings(tmp_path, {"otherKey": 1})
    bak = doorway.backup_settings(path)
    assert bak and os.path.exists(bak)
    assert json.load(open(bak)) == {"otherKey": 1}
    doorway.write_settings(path, {"otherKey": 2})
    assert json.load(open(path)) == {"otherKey": 2}
    assert json.load(open(bak)) == {"otherKey": 1}   # backup untouched


def test_backup_of_a_missing_file_is_none(tmp_path):
    assert doorway.backup_settings(str(tmp_path / "nope.json")) is None


# --------------------------------------------------------------------------
# the gate itself — keyless, config-free, fires on a contradicted repo
# --------------------------------------------------------------------------

def test_the_gate_blocks_a_contradicted_repo_with_no_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HELICON_HOME", str(tmp_path / "home"))
    repo = _git_repo(tmp_path / "repo", {
        "CLAUDE.md": "Config lives in `config/settings.yaml`.\n",
        "main.py": "x = 1\n"})
    from helicon.db import init_db
    from helicon.capture import hook_gate
    conn = init_db(doorway.user_db_path())
    g = hook_gate(conn, repo, "sess", "do the thing")
    assert g and g["action"] == "block"
    assert "config/settings.yaml" in g["message"]
    # and it logged the block into the gate's own store
    f = doorway.last_fired(doorway.user_db_path())
    assert f and f["kind"] == "gate_blocked"


def test_the_gate_allows_a_repo_whose_docs_agree(tmp_path, monkeypatch):
    monkeypatch.setenv("HELICON_HOME", str(tmp_path / "home"))
    repo = _git_repo(tmp_path / "repo", {
        "CLAUDE.md": "The entry point is `main.py`.\n", "main.py": "x = 1\n"})
    from helicon.db import init_db
    from helicon.capture import hook_gate
    conn = init_db(doorway.user_db_path())
    assert hook_gate(conn, repo, "sess", "go") is None


def test_last_fired_is_none_before_the_store_exists(tmp_path):
    assert doorway.last_fired(str(tmp_path / "none.db")) is None


# --------------------------------------------------------------------------
# where the gate logs — a configured user's block belongs in their own store,
# so it shows up in the dashboard / `helicon runs`, not a hidden side-DB
# --------------------------------------------------------------------------

def test_gate_logs_into_the_configured_store_when_one_exists(tmp_path, monkeypatch):
    # config.py captures CONFIG_FILE at import (fine in production — the hook is
    # a fresh process each call); steer it directly so the test is order-proof.
    monkeypatch.delenv("HELICON_HOME", raising=False)
    monkeypatch.delenv("HELICON_CONFIG", raising=False)
    cfg = tmp_path / "config.json"
    store = tmp_path / "mystore" / "helicon.db"
    cfg.write_text(json.dumps({"db_path": str(store)}))
    monkeypatch.setattr("helicon.config.CONFIG_FILE", str(cfg))
    assert doorway.gate_db_path() == str(store)


def test_a_stranger_with_no_config_keeps_the_standalone_store(tmp_path, monkeypatch):
    monkeypatch.setenv("HELICON_HOME", str(tmp_path / "home"))
    # HELICON_HOME forces the config-free store even if a config is around
    assert doorway.gate_db_path() == doorway.user_db_path()
