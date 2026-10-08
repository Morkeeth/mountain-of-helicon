"""Token accounting: /llm/stats must reflect durable usage in llm_cache,
not just the calling process's in-memory _call_log (CLI runs like
`helicon report --llm` happen in other processes)."""

import sqlite3

import pytest

from helicon import llm
from helicon.llm import call_cost, get_call_stats, get_route_stats, model_prices


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE llm_cache (
        cache_key TEXT PRIMARY KEY,
        model TEXT NOT NULL,
        operation TEXT DEFAULT '',
        response TEXT NOT NULL,
        input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""")
    c.executemany(
        "INSERT INTO llm_cache VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("k1", "model-main", "battery_judge", "{}", 1000, 2000, "2026-07-05T10:00:00"),
            ("k2", "model-main", "pair_judge", "{}", 500, 500, "2026-07-05T11:00:00"),
            ("k3", "model-small", "summarize", "{}", 100, 50, "2026-07-05T12:00:00"),
        ],
    )
    yield c
    c.close()


@pytest.fixture(autouse=True)
def clean_memory_state(monkeypatch):
    monkeypatch.setattr(llm, "_call_log", [])
    monkeypatch.setattr(llm, "_cache", {})
    monkeypatch.setattr(llm, "_cache_stats", {"hits": 0, "misses": 0})
    monkeypatch.setattr(llm, "_db_conn", None)


def test_stats_come_from_db_even_with_empty_call_log(conn):
    """The bug: CLI processes wrote usage to llm_cache, but the API server's
    _call_log was empty, so the dashboard showed no activity."""
    stats = get_call_stats(conn)
    assert stats["total_calls"] == 3
    plus = stats["by_model"]["model-main"]
    assert plus["calls"] == 2
    assert plus["input_tokens"] == 1500
    assert plus["output_tokens"] == 2500
    assert stats["by_model"]["model-small"]["calls"] == 1


# USD per million tokens, as the user would write them in config.
PRICES = {"llm_prices": {"model-main": {"input": 0.4, "output": 1.2},
                         "model-small": {"input": 0.1, "output": 0.3}}}


def test_no_price_configured_means_cost_unknown_never_a_number(conn):
    stats = get_call_stats(conn)
    for row in stats["by_model"].values():
        assert row["cost_usd"] is None
    assert stats["total_cost_usd"] is None
    assert stats["unpriced_models"] == ["model-main", "model-small"]


def test_cost_comes_from_the_configured_price(conn):
    stats = get_call_stats(conn, PRICES)
    main = stats["by_model"]["model-main"]
    # 1500 input and 2500 output tokens at 0.4 and 1.2 per million.
    assert main["cost_usd"] == pytest.approx((1500 * 0.4 + 2500 * 1.2) / 1e6)
    small = stats["by_model"]["model-small"]
    assert small["cost_usd"] == pytest.approx((100 * 0.1 + 50 * 0.3) / 1e6)
    assert stats["total_cost_usd"] == pytest.approx(main["cost_usd"] + small["cost_usd"])
    assert stats["unpriced_models"] == []


def test_one_unpriced_model_makes_the_total_unknown(conn):
    only_main = {"llm_prices": {"model-main": PRICES["llm_prices"]["model-main"]}}
    stats = get_call_stats(conn, only_main)
    assert stats["by_model"]["model-main"]["cost_usd"] > 0
    assert stats["by_model"]["model-small"]["cost_usd"] is None
    assert stats["total_cost_usd"] is None      # a total with a hole is not a total
    assert stats["unpriced_models"] == ["model-small"]


def test_a_configured_price_of_zero_is_a_real_zero(conn):
    # A local model costs nothing, and the user can say so. That is measured,
    # which is different from the unknown above.
    free = {"llm_prices": {m: {"input": 0, "output": 0} for m in ("model-main", "model-small")}}
    stats = get_call_stats(conn, free)
    assert stats["total_cost_usd"] == 0 and stats["unpriced_models"] == []


def test_malformed_prices_are_dropped_not_guessed():
    cfg = {"llm_prices": {"a": {"input": 1}, "b": {"input": "1", "output": 2},
                          "c": {"input": -1, "output": 2}, "d": 3,
                          "e": {"input": True, "output": 1},
                          "ok": {"input": 1, "output": 2}}}
    assert model_prices(cfg) == {"ok": (1.0, 2.0)}
    assert model_prices({}) == {} and model_prices(None) == {}
    assert model_prices({"llm_prices": "cheap"}) == {}
    assert call_cost("a", 1000, 1000, model_prices(cfg)) is None
    assert call_cost("ok", 1_000_000, 500_000, model_prices(cfg)) == pytest.approx(2.0)


class _Usage:
    prompt_tokens, completion_tokens = 1000, 500


class _Client:
    def __init__(self):
        from types import SimpleNamespace as NS
        create = lambda **kw: NS(choices=[NS(message=NS(content="ok"))], usage=_Usage())
        self.chat = NS(completions=NS(create=create))


def test_a_live_call_logs_unknown_cost_without_a_price(monkeypatch):
    monkeypatch.setattr(llm, "_route_log", [])
    assert llm.complete(_Client(), "s", "u", model="unpriced-model", operation="op") == "ok"
    assert llm._call_log[-1]["cost_usd"] is None
    assert get_route_stats()["operations"]["op"]["total_cost"] is None


def test_a_live_call_logs_the_configured_cost(monkeypatch):
    monkeypatch.setattr(llm, "_route_log", [])
    client = _Client()
    client._helicon_prices = model_prices({"llm_prices": {"m": {"input": 2, "output": 4}}})
    assert llm.complete(client, "s", "u", model="m", operation="op") == "ok"
    assert llm._call_log[-1]["cost_usd"] == pytest.approx((1000 * 2 + 500 * 4) / 1e6)
    assert get_route_stats()["operations"]["op"]["total_cost"] == pytest.approx(0.004)


def test_no_fallback_price_constant_is_left_in_the_model_layer():
    import inspect
    src = inspect.getsource(llm)
    assert "0.001" not in src and "PER_1K" not in src


def test_session_overlay_adds_cache_hits_and_latency(conn):
    llm._call_log.extend([
        {"model": "model-main", "elapsed": 0.0, "input_tokens": 0,
         "output_tokens": 0, "timestamp": 0, "cached": True, "operation": "x"},
        {"model": "model-main", "elapsed": 4.0, "input_tokens": 1000,
         "output_tokens": 2000, "timestamp": 0, "cached": False,
         "operation": "x", "cost_usd": None},
    ])
    stats = get_call_stats(conn)
    plus = stats["by_model"]["model-main"]
    # live call is already in llm_cache (choke point writes it): no double count
    assert plus["calls"] == 2
    assert plus["cached_calls"] == 1
    assert plus["avg_latency"] == 4.0
    assert stats["total_calls"] == 4  # 3 db live + 1 session cache hit


def test_fallback_to_memory_when_no_db():
    llm._call_log.append(
        {"model": "model-main", "elapsed": 1.0, "input_tokens": 10,
         "output_tokens": 20, "timestamp": 0, "cached": False,
         "operation": "x", "cost_usd": None}
    )
    stats = get_call_stats(None)
    assert stats["total_calls"] == 1
    assert stats["by_model"]["model-main"]["input_tokens"] == 10
    assert stats["by_model"]["model-main"]["cost_usd"] is None
    assert stats["total_cost_usd"] is None


def test_empty_everything():
    stats = get_call_stats(None)
    assert stats == {
        "total_calls": 0,
        "by_model": {},
        "by_operation": {},
        "cache": {"hits": 0, "misses": 0, "rate": 0.0, "entries": 0},
        "total_cost_usd": 0,      # nothing was called, so nothing was spent
        "unpriced_models": [],
    }
    assert get_route_stats() == {"operations": {}}
