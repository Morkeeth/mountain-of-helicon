"""The model layer is provider-neutral and has no memory of its first vendor.

Three promises, each pinned here:
  1. Resolution order: config key, then the HELICON_LLM_* env.
  2. Settings from before the layer went neutral are ignored. A config that
     only has those means "no model configured", and doctor says so in one line.
  3. Nothing configured means OFF with a plain message. No default vendor, no
     guessed model name.

No test here talks to a network. Building a client opens no connection, and
every completion goes through a fake.
"""
import json

import pytest

from helicon.config import ignored_old_llm_settings, load_config, resolve_llm

# The settings Helicon no longer reads, spelled once for the tests below.
OLD_KEY, OLD_URL, OLD_MODEL, OLD_TIERS = (
    "qwen_api_key", "qwen_base_url", "qwen_model", "qwen_models")
OLD_ENV = "QWEN_API_KEY"

_ENV = ("HELICON_LLM_API_KEY", "HELICON_LLM_BASE_URL", "HELICON_LLM_MODEL",
        OLD_ENV, "HELICON_CONFIG")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    # The developer's shell may carry a real key. None of it reaches a test.
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HELICON_HOME", str(tmp_path / "home"))


def _config(tmp_path, data: dict) -> dict:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"db_path": str(tmp_path / "h.db"), **data}))
    return load_config(str(path))


# --- 1. resolution order ---------------------------------------------------

def test_config_key_wins_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HELICON_LLM_API_KEY", "env-neutral")
    cfg = _config(tmp_path, {"llm_api_key": "file-neutral"})
    r = resolve_llm(cfg)
    assert r["api_key"] == "file-neutral"
    assert r["key_source"] == "config llm_api_key"


def test_env_is_the_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("HELICON_LLM_API_KEY", "env-neutral")
    r = resolve_llm(_config(tmp_path, {}))
    assert r["api_key"] == "env-neutral"
    assert r["key_source"] == "HELICON_LLM_API_KEY env"


def test_base_url_and_model_follow_the_same_order(tmp_path, monkeypatch):
    monkeypatch.setenv("HELICON_LLM_BASE_URL", "http://env.example/v1")
    monkeypatch.setenv("HELICON_LLM_MODEL", "env-model")
    r = resolve_llm(_config(tmp_path, {}))
    assert (r["base_url"], r["model"]) == ("http://env.example/v1", "env-model")
    r = resolve_llm(_config(tmp_path, {"llm_base_url": "http://file.example/v1",
                                       "llm_model": "file-model"}))
    assert (r["base_url"], r["model"]) == ("http://file.example/v1", "file-model")


def test_status_never_carries_the_key(tmp_path):
    from helicon.llm import llm_status
    status = llm_status(_config(tmp_path, {"llm_api_key": "sk-secret-value",
                                           "llm_base_url": "http://x.example/v1",
                                           "llm_model": "m"}))
    assert status["enabled"] is True
    assert "sk-secret-value" not in json.dumps(status)


# --- 2. old settings are ignored --------------------------------------------

def test_old_only_config_means_no_model_configured(tmp_path, monkeypatch):
    from helicon.llm import get_client, resolve_model
    monkeypatch.setenv(OLD_ENV, "env-old")
    cfg = _config(tmp_path, {OLD_KEY: "file-old", OLD_URL: "http://old.example/v1",
                             OLD_MODEL: "old-model", OLD_TIERS: {"fast": "old-fast"}})
    r = resolve_llm(cfg)
    assert r["enabled"] is False
    assert "no model configured" in r["reason"]
    assert (r["api_key"], r["base_url"], r["model"]) == ("", "", "")
    assert get_client(cfg) is None
    for tier in ("fast", "default", "deep"):
        assert resolve_model(tier, cfg) is None


def test_old_settings_do_not_leak_into_a_neutral_config(tmp_path, monkeypatch):
    from helicon.llm import resolve_model
    monkeypatch.setenv(OLD_ENV, "env-old")
    cfg = _config(tmp_path, {"llm_base_url": "http://x.example/v1", "llm_model": "main",
                             OLD_KEY: "file-old", OLD_TIERS: {"fast": "old-fast"}})
    r = resolve_llm(cfg)
    assert r["enabled"] is True and r["api_key"] == ""
    assert resolve_model("fast", cfg) == "main"


def test_ignored_old_settings_are_named_never_valued(tmp_path, monkeypatch):
    monkeypatch.setenv(OLD_ENV, "env-old-secret")
    cfg = _config(tmp_path, {OLD_KEY: "file-old-secret", OLD_URL: ""})
    found = ignored_old_llm_settings(cfg)
    assert found == [OLD_KEY, f"{OLD_ENV} env"]
    assert "secret" not in " ".join(found)
    monkeypatch.delenv(OLD_ENV)
    assert ignored_old_llm_settings(_config(tmp_path, {"llm_model": "m"})) == []


def test_load_config_does_not_rewrite_the_file(tmp_path):
    path = tmp_path / "config.json"
    before = json.dumps({"db_path": str(tmp_path / "h.db"), OLD_KEY: "file-old"})
    path.write_text(before)
    cfg = load_config(str(path))
    resolve_llm(cfg)
    assert path.read_text() == before


def test_no_second_judge_unless_the_config_names_one(tmp_path):
    pytest.importorskip("openai")
    from helicon.llm import default_model, get_client
    base = {"llm_base_url": "http://x.example/v1", "llm_model": "main"}
    assert default_model(get_client(_config(tmp_path, base)), "judge2") is None
    named = get_client(_config(tmp_path, {**base, "llm_judge2_model": "second"}))
    assert default_model(named, "judge2") == "second"


# --- 3. nothing configured means off, said plainly -------------------------

def test_nothing_configured_is_off_with_a_plain_message(tmp_path):
    from helicon.llm import get_client, llm_status, resolve_model
    cfg = _config(tmp_path, {})
    status = llm_status(cfg)
    assert status["enabled"] is False
    assert "no model configured" in status["reason"]
    assert "llm_base_url" in status["reason"]
    assert status["base_url"] == ""            # no silent default vendor
    assert get_client(cfg) is None
    assert resolve_model("default", cfg) is None   # no guessed model name
    assert get_client({}) is None and resolve_model("default") is None


def test_neutral_key_alone_gets_no_default_vendor(tmp_path):
    from helicon.llm import get_client
    cfg = _config(tmp_path, {"llm_api_key": "k"})
    r = resolve_llm(cfg)
    assert r["enabled"] is False and r["base_url"] == ""
    assert "no endpoint" in r["reason"]
    assert get_client(cfg) is None


def test_endpoint_without_a_model_name_is_off(tmp_path):
    r = resolve_llm(_config(tmp_path, {"llm_api_key": "k",
                                       "llm_base_url": "http://x.example/v1"}))
    assert r["enabled"] is False
    assert "llm_model" in r["reason"]


def test_local_endpoint_needs_no_key(tmp_path):
    pytest.importorskip("openai")
    from helicon.llm import default_model, get_client, resolve_model
    cfg = _config(tmp_path, {"llm_base_url": "http://localhost:11434/v1",
                             "llm_model": "local-model"})
    assert resolve_llm(cfg)["enabled"] is True
    client = get_client(cfg)
    assert client is not None
    assert default_model(client) == "local-model"
    assert resolve_model("fast", cfg) == "local-model"


def test_neutral_tiers_can_be_named_one_by_one(tmp_path):
    from helicon.llm import resolve_model
    cfg = _config(tmp_path, {"llm_base_url": "http://x.example/v1", "llm_model": "main",
                             "llm_models": {"fast": "small"}})
    assert resolve_model("fast", cfg) == "small"
    assert resolve_model("deep", cfg) == "main"


class _FakeClient:
    """Records the request and answers from memory. No network."""

    def __init__(self):
        self.models_seen = []
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.models_seen.append(kwargs["model"])
                msg = type("M", (), {"content": "ok"})()
                return type("R", (), {"choices": [type("C", (), {"message": msg})()],
                                      "usage": None})()

        self.chat = type("Chat", (), {"completions": _Completions()})()


@pytest.fixture
def clean_llm(monkeypatch):
    import helicon.llm as llm
    monkeypatch.setattr(llm, "_cache", {})
    monkeypatch.setattr(llm, "_call_log", [])
    monkeypatch.setattr(llm, "_route_log", [])
    monkeypatch.setattr(llm, "_cache_stats", {"hits": 0, "misses": 0})
    monkeypatch.setattr(llm, "_db_conn", None)
    monkeypatch.setattr(llm, "_warned_no_model", False)
    return llm


def test_complete_without_a_model_says_so_and_does_not_guess(clean_llm, capsys):
    client = _FakeClient()
    assert clean_llm.complete(client, "sys", "user", operation="probe") == ""
    assert client.models_seen == []            # nothing was sent anywhere
    captured = capsys.readouterr()
    assert "model not configured" in captured.err
    assert captured.out == ""                  # stdout stays clean for --json


def test_complete_uses_the_model_the_client_was_configured_with(clean_llm):
    client = _FakeClient()
    client._helicon_models = {"fast": "small", "default": "main", "deep": "big"}
    assert clean_llm.complete(client, "sys", "user") == "ok"
    assert clean_llm.complete(client, "sys", "other", model="explicit") == "ok"
    assert client.models_seen == ["main", "explicit"]


def test_no_vendor_model_name_is_a_default_argument():
    # A default in a signature is a guess made for every caller at once.
    import inspect
    from helicon import battery, identity, llm, pairing, report, rot, rules, writeback
    for mod in (battery, identity, llm, pairing, report, rot, rules, writeback):
        for name, fn in inspect.getmembers(mod, inspect.isfunction):
            if fn.__module__ != mod.__name__:
                continue
            for p in inspect.signature(fn).parameters.values():
                if "model" in p.name and isinstance(p.default, str):
                    pytest.fail(f"{mod.__name__}.{name}({p.name}={p.default!r})")


# --- the old module name is gone ---------------------------------------------

def test_old_module_name_is_gone():
    # Asked of THIS package directory. A plain import can be answered by an
    # editable install of another checkout, which would hide a real removal.
    import helicon
    from importlib.machinery import PathFinder
    old_name = "helicon." + OLD_KEY.split("_")[0]
    assert PathFinder.find_spec(old_name, helicon.__path__) is None


# --- the cache table is renamed in place ------------------------------------

_OLD_TABLE = OLD_KEY.split("_")[0] + "_cache"
_ROWS = [("k1", "model-a", "summarize", '{"a": 1}', 10, 20, "2026-07-01T00:00:00"),
         ("k2", "model-b", "", "plain text", 3, 4, "2026-07-02T00:00:00")]


def _old_db(path):
    """A database as an install from before the rename left it: the cache
    under its first name, with rows in it."""
    import sqlite3
    conn = sqlite3.connect(str(path))
    conn.execute(f"""CREATE TABLE {_OLD_TABLE} (
        cache_key TEXT PRIMARY KEY, model TEXT NOT NULL, operation TEXT DEFAULT '',
        response TEXT NOT NULL, input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0, created_at TEXT NOT NULL)""")
    conn.executemany(f"INSERT INTO {_OLD_TABLE} VALUES (?,?,?,?,?,?,?)", _ROWS)
    conn.commit()
    conn.close()


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _cache_rows(conn):
    return [tuple(r) for r in conn.execute("SELECT * FROM llm_cache ORDER BY cache_key")]


def test_init_db_renames_a_populated_old_cache_and_keeps_every_row(tmp_path):
    from helicon.db import init_db
    path = tmp_path / "old.db"
    _old_db(path)
    conn = init_db(str(path))
    assert _OLD_TABLE not in _tables(conn) and "llm_cache" in _tables(conn)
    assert _cache_rows(conn) == _ROWS
    conn.close()
    # Twice is a no-op: same rows, still one table.
    conn = init_db(str(path))
    assert _OLD_TABLE not in _tables(conn)
    assert _cache_rows(conn) == _ROWS
    conn.close()


def test_migration_reports_what_it_did_and_does_nothing_the_second_time(tmp_path):
    import sqlite3
    from helicon.db import migrate_llm_cache
    path = tmp_path / "old.db"
    _old_db(path)
    conn = sqlite3.connect(str(path))
    assert migrate_llm_cache(conn) is True
    assert migrate_llm_cache(conn) is False
    assert _cache_rows(conn) == _ROWS
    # The primary key came along: a cache write still replaces, never duplicates.
    conn.execute("INSERT OR REPLACE INTO llm_cache VALUES (?,?,?,?,?,?,?)", _ROWS[0])
    assert len(_cache_rows(conn)) == len(_ROWS)


def test_fresh_database_gets_the_new_name_only(tmp_path):
    import sqlite3
    import helicon.llm as llm
    from helicon.db import init_db, migrate_llm_cache
    conn = init_db(str(tmp_path / "fresh.db"))
    assert migrate_llm_cache(conn) is False
    saved = dict(llm._cache)
    try:
        llm.load_cache_from_db(conn)
    finally:
        llm._cache.clear()
        llm._cache.update(saved)
    assert "llm_cache" in _tables(conn) and _OLD_TABLE not in _tables(conn)
    assert isinstance(conn, sqlite3.Connection)


def test_lazy_create_migrates_first_so_old_rows_are_not_stranded(tmp_path):
    # load_cache_from_db can meet an old database before init_db does. A bare
    # CREATE TABLE IF NOT EXISTS there would leave two tables and an empty cache.
    import sqlite3
    import helicon.llm as llm
    path = tmp_path / "old.db"
    _old_db(path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    saved = dict(llm._cache)
    try:
        llm._cache.clear()
        llm.load_cache_from_db(conn)
        assert llm._cache == {"k1": '{"a": 1}', "k2": "plain text"}
    finally:
        llm._cache.clear()
        llm._cache.update(saved)
    assert _OLD_TABLE not in _tables(conn)
    assert _cache_rows(conn) == _ROWS


def test_both_tables_present_is_left_alone(tmp_path):
    # Not a state this code produces. If it is ever met, nothing is dropped.
    import sqlite3
    from helicon.db import migrate_llm_cache
    path = tmp_path / "both.db"
    _old_db(path)
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE llm_cache (cache_key TEXT PRIMARY KEY)")
    assert migrate_llm_cache(conn) is False
    assert conn.execute(f"SELECT COUNT(*) FROM {_OLD_TABLE}").fetchone()[0] == len(_ROWS)


# --- embeddings: local unless the config names an endpoint -------------------

def _provider(monkeypatch, config):
    from helicon import embeddings
    monkeypatch.setattr(embeddings, "_provider_cache", None)
    monkeypatch.setattr("helicon.config.load_config", lambda path=None: config)
    return embeddings._embed_provider()


def test_embeddings_default_to_local_minilm(monkeypatch):
    assert _provider(monkeypatch, {})[0::2] == ("local", "all-MiniLM-L6-v2")
    assert _provider(monkeypatch, {})[3] == 384


def test_a_router_key_alone_does_not_pick_an_embeddings_vendor(monkeypatch):
    # A key for the judge bench is not a decision about where memories are sent.
    kind, client, model, dim = _provider(monkeypatch, {"openrouter_api_key": "k"})
    assert (kind, client, model, dim) == ("local", None, "all-MiniLM-L6-v2", 384)


def test_incomplete_embeddings_block_stays_local(monkeypatch):
    for block in ({"api_key": "k", "base_url": "http://x.example/v1"},
                  {"base_url": "http://x.example/v1", "model": "m"},
                  {"api_key": "k", "model": "m", "dim": 8}):
        assert _provider(monkeypatch, {"embeddings": block})[0] == "local", block


def test_complete_embeddings_block_is_used_as_written(monkeypatch):
    pytest.importorskip("openai")
    kind, client, model, dim = _provider(monkeypatch, {"embeddings": {
        "base_url": "http://localhost:9/v1", "model": "my-embedder", "dim": 8}})
    assert (kind, model, dim) == ("remote", "my-embedder", 8)
    assert str(client.base_url).rstrip("/") == "http://localhost:9/v1"


def test_retrieval_has_no_reranker_left():
    from helicon import embeddings
    assert not [n for n in dir(embeddings) if "rerank" in n.lower()]


# --- first run: init and doctor --------------------------------------------

def _cli(home, *args, extra_env=None):
    import os
    import subprocess
    import sys
    from pathlib import Path
    env = dict(os.environ)
    for name in _ENV:
        env.pop(name, None)
    env.pop("HELICON_HOME", None)
    env["HOME"] = str(home)
    env.update(extra_env or {})
    return subprocess.run([sys.executable, "-m", "helicon", *args],
                          cwd=Path(__file__).resolve().parents[1], env=env,
                          capture_output=True, text=True)


def test_init_writes_no_vendor_and_says_what_works_keyless(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    run = _cli(home, "init")
    assert run.returncode == 0, run.stderr
    text = (home / ".helicon" / "config.json").read_text()
    written = json.loads(text)
    assert written["llm_api_key"] == "" and written["llm_base_url"] == ""
    assert written["llm_model"] == ""
    assert "dashscope" not in text.lower() and "qwen" not in text.lower()
    out = run.stdout
    assert "Qwen" not in out and "alibaba" not in out.lower()
    assert "any OpenAI-compatible endpoint" in out and "including a local one" in out
    for works in ("deterministic review", "truth", "start card", "guard", "decay"):
        assert works in out, works
    assert "HELICON_LLM_API_KEY" in out


def test_init_ignores_the_old_env_key(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    run = _cli(home, "init", extra_env={OLD_ENV: "old-test-key"})
    assert run.returncode == 0, run.stderr
    text = (home / ".helicon" / "config.json").read_text()
    written = json.loads(text)
    assert written["llm_api_key"] == "" and OLD_KEY not in written
    assert "old-test-key" not in text + run.stdout + run.stderr
    assert resolve_llm(written)["enabled"] is False


def test_doctor_says_old_settings_are_ignored_in_one_line(tmp_path):
    home = tmp_path / "home"
    (home / ".helicon").mkdir(parents=True)
    cfg = {"db_path": str(home / ".helicon" / "helicon.db"),
           OLD_KEY: "sk-old-secret", OLD_URL: "http://old.example/v1"}
    (home / ".helicon" / "config.json").write_text(json.dumps(cfg))
    out = _cli(home, "doctor", extra_env={OLD_ENV: "sk-env-secret"}).stdout
    assert "model features off:" in out and "no model configured" in out
    lines = [ln for ln in out.splitlines() if "old Qwen settings found and ignored" in ln]
    assert len(lines) == 1, out
    for name in (OLD_KEY, OLD_URL, f"{OLD_ENV} env", "llm_base_url", "llm_model",
                 "llm_api_key", "HELICON_LLM_BASE_URL"):
        assert name in lines[0], name
    assert "secret" not in out and "old.example" not in out


def test_doctor_names_the_source_and_never_the_key(tmp_path):
    home = tmp_path / "home"
    (home / ".helicon").mkdir(parents=True)
    cfg = {"db_path": str(home / ".helicon" / "helicon.db"),
           "llm_api_key": "sk-doctor-secret", "llm_base_url": "http://localhost:9/v1",
           "llm_model": "local-model"}
    (home / ".helicon" / "config.json").write_text(json.dumps(cfg))
    out = _cli(home, "doctor").stdout
    assert "model configured" in out and "config llm_api_key" in out
    assert "sk-doctor-secret" not in out
    assert "Qwen" not in out


def test_doctor_with_nothing_configured_says_off_and_what_still_works(tmp_path):
    home = tmp_path / "home"
    (home / ".helicon").mkdir(parents=True)
    (home / ".helicon" / "config.json").write_text(
        json.dumps({"db_path": str(home / ".helicon" / "helicon.db")}))
    out = _cli(home, "doctor").stdout
    assert "model features off:" in out and "no model configured" in out
    assert "including a local one" in out
    assert "Qwen" not in out
