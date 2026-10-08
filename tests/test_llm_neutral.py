"""The model layer is provider-neutral, and an old config still works.

Three promises, each pinned here:
  1. Resolution order: neutral config key, neutral env, old qwen_* config key,
     old QWEN_API_KEY env.
  2. A config that only has qwen_* keys behaves exactly as it did before.
  3. Nothing configured means OFF with a plain message. No default vendor, no
     guessed model name.

No test here talks to a network. Building a client opens no connection, and
every completion goes through a fake.
"""
import json

import pytest

from helicon.config import LEGACY_LLM_BASE_URL, load_config, resolve_llm

_ENV = ("HELICON_LLM_API_KEY", "HELICON_LLM_BASE_URL", "HELICON_LLM_MODEL",
        "QWEN_API_KEY", "DASHSCOPE_API_KEY", "HELICON_CONFIG")


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

def test_neutral_config_key_wins_over_everything(tmp_path, monkeypatch):
    monkeypatch.setenv("HELICON_LLM_API_KEY", "env-neutral")
    monkeypatch.setenv("QWEN_API_KEY", "env-old")
    cfg = _config(tmp_path, {"llm_api_key": "file-neutral", "qwen_api_key": "file-old"})
    r = resolve_llm(cfg)
    assert r["api_key"] == "file-neutral"
    assert r["key_source"] == "config llm_api_key"


def test_neutral_env_beats_both_old_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("HELICON_LLM_API_KEY", "env-neutral")
    monkeypatch.setenv("QWEN_API_KEY", "env-old")
    r = resolve_llm(_config(tmp_path, {"qwen_api_key": "file-old"}))
    assert r["api_key"] == "env-neutral"
    assert r["key_source"] == "HELICON_LLM_API_KEY env"


def test_old_config_key_beats_old_env(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_API_KEY", "env-old")
    r = resolve_llm(_config(tmp_path, {"qwen_api_key": "file-old"}))
    assert r["api_key"] == "file-old"
    assert r["key_source"] == "config qwen_api_key"


def test_old_env_is_the_last_source(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_API_KEY", "env-old")
    r = resolve_llm(_config(tmp_path, {}))
    assert r["api_key"] == "env-old"
    assert r["key_source"] == "QWEN_API_KEY env"


def test_base_url_and_model_follow_the_same_order(tmp_path, monkeypatch):
    monkeypatch.setenv("HELICON_LLM_BASE_URL", "http://env.example/v1")
    monkeypatch.setenv("HELICON_LLM_MODEL", "env-model")
    old = {"qwen_base_url": "http://old.example/v1"}
    r = resolve_llm(_config(tmp_path, old))
    assert (r["base_url"], r["model"]) == ("http://env.example/v1", "env-model")
    r = resolve_llm(_config(tmp_path, {**old, "llm_base_url": "http://file.example/v1",
                                       "llm_model": "file-model"}))
    assert (r["base_url"], r["model"]) == ("http://file.example/v1", "file-model")
    monkeypatch.delenv("HELICON_LLM_BASE_URL")
    r = resolve_llm(_config(tmp_path, old))
    assert r["base_url"] == "http://old.example/v1"
    assert r["base_url_source"] == "config qwen_base_url"


def test_status_never_carries_the_key(tmp_path):
    from helicon.llm import llm_status
    status = llm_status(_config(tmp_path, {"llm_api_key": "sk-secret-value",
                                           "llm_base_url": "http://x.example/v1",
                                           "llm_model": "m"}))
    assert status["enabled"] is True
    assert "sk-secret-value" not in json.dumps(status)


# --- 2. an old config is unchanged -----------------------------------------

def test_old_only_config_resolves_as_before(tmp_path):
    from helicon.llm import MODELS, resolve_model
    cfg = _config(tmp_path, {"qwen_api_key": "file-old",
                             "qwen_base_url": "http://old.example/v1"})
    r = resolve_llm(cfg)
    assert r["enabled"] is True
    assert (r["api_key"], r["base_url"]) == ("file-old", "http://old.example/v1")
    assert cfg["qwen_api_key"] == "file-old"
    for tier in ("fast", "default", "deep"):
        assert resolve_model(tier, cfg) == MODELS[tier]


def test_old_key_without_base_url_keeps_the_endpoint_it_implied(tmp_path):
    r = resolve_llm(_config(tmp_path, {"qwen_api_key": "file-old"}))
    assert r["enabled"] is True
    assert r["base_url"] == LEGACY_LLM_BASE_URL
    assert r["base_url_source"] == "legacy default"


def test_old_tier_override_still_applies(tmp_path):
    from helicon.llm import MODELS, resolve_model
    cfg = _config(tmp_path, {"qwen_api_key": "k", "qwen_models": {"fast": "my-fast"}})
    assert resolve_model("fast", cfg) == "my-fast"
    assert resolve_model("deep", cfg) == MODELS["deep"]


def test_old_init_config_with_empty_key_stays_off(tmp_path):
    # What `helicon init` wrote before: the endpoint and an empty key slot.
    from helicon.llm import get_client
    cfg = _config(tmp_path, {"qwen_api_key": "", "qwen_model": "qwen3.6-plus",
                             "qwen_base_url": LEGACY_LLM_BASE_URL})
    assert resolve_llm(cfg)["enabled"] is False
    assert get_client(cfg) is None


def test_load_config_does_not_rewrite_the_file(tmp_path):
    path = tmp_path / "config.json"
    before = json.dumps({"db_path": str(tmp_path / "h.db"), "qwen_api_key": "file-old"})
    path.write_text(before)
    cfg = load_config(str(path))
    resolve_llm(cfg)
    assert path.read_text() == before


def test_old_client_carries_the_old_models(tmp_path):
    pytest.importorskip("openai")
    from helicon.llm import MODELS, default_model, get_client
    client = get_client(_config(tmp_path, {"qwen_api_key": "file-old"}))
    assert str(client.base_url).rstrip("/") == LEGACY_LLM_BASE_URL
    assert default_model(client) == MODELS["default"]
    assert default_model(client, "fast") == MODELS["fast"]


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


# --- the shim ---------------------------------------------------------------

def test_old_import_path_still_works():
    from helicon.qwen import (complete, complete_json, detect_contradictions,
                              get_client, resolve_model, set_cache_db)
    import helicon.llm as llm
    assert complete is llm.complete and complete_json is llm.complete_json
    assert get_client is llm.get_client and resolve_model is llm.resolve_model
    assert detect_contradictions is llm.detect_contradictions
    assert set_cache_db is llm.set_cache_db


def test_shim_and_new_module_are_one_module(monkeypatch):
    # One object, so the cache, the call log and a monkeypatch are shared.
    import helicon.llm as llm
    import helicon.qwen as old
    from helicon import qwen
    assert old is llm and qwen is llm
    assert old._cache is llm._cache and old._call_log is llm._call_log
    monkeypatch.setattr("helicon.qwen.complete_json", lambda *a, **kw: {"patched": True})
    assert llm.complete_json(None, "", "") == {"patched": True}


def test_cache_table_keeps_its_name():
    # Users' databases hold this table. The rename stops at the Python layer.
    import sqlite3
    import helicon.llm as llm
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    saved = dict(llm._cache)
    try:
        llm.load_cache_from_db(conn)
    finally:
        llm._cache.clear()
        llm._cache.update(saved)
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert "qwen_cache" in names
