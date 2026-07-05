"""Token accounting: /qwen/stats must reflect durable usage in qwen_cache,
not just the calling process's in-memory _call_log (CLI runs like
`helicon report --llm` happen in other processes)."""

import sqlite3

import pytest

from helicon import qwen
from helicon.qwen import get_call_stats, TIER_COST_PER_1K


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE qwen_cache (
        cache_key TEXT PRIMARY KEY,
        model TEXT NOT NULL,
        operation TEXT DEFAULT '',
        response TEXT NOT NULL,
        input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""")
    c.executemany(
        "INSERT INTO qwen_cache VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("k1", "qwen3.6-plus", "battery_judge", "{}", 1000, 2000, "2026-07-05T10:00:00"),
            ("k2", "qwen3.6-plus", "pair_judge", "{}", 500, 500, "2026-07-05T11:00:00"),
            ("k3", "qwen3.6-flash", "summarize", "{}", 100, 50, "2026-07-05T12:00:00"),
        ],
    )
    yield c
    c.close()


@pytest.fixture(autouse=True)
def clean_memory_state(monkeypatch):
    monkeypatch.setattr(qwen, "_call_log", [])
    monkeypatch.setattr(qwen, "_cache", {})
    monkeypatch.setattr(qwen, "_cache_stats", {"hits": 0, "misses": 0})
    monkeypatch.setattr(qwen, "_db_conn", None)


def test_stats_come_from_db_even_with_empty_call_log(conn):
    """The bug: CLI processes wrote usage to qwen_cache, but the API server's
    _call_log was empty, so the dashboard showed no activity."""
    stats = get_call_stats(conn)
    assert stats["total_calls"] == 3
    plus = stats["by_model"]["qwen3.6-plus"]
    assert plus["calls"] == 2
    assert plus["input_tokens"] == 1500
    assert plus["output_tokens"] == 2500
    expected_cost = 4000 / 1000 * TIER_COST_PER_1K["qwen3.6-plus"]
    assert plus["cost_usd"] == pytest.approx(expected_cost)
    assert stats["by_model"]["qwen3.6-flash"]["calls"] == 1
    assert stats["total_cost_usd"] > 0


def test_session_overlay_adds_cache_hits_and_latency(conn):
    qwen._call_log.extend([
        {"model": "qwen3.6-plus", "elapsed": 0.0, "input_tokens": 0,
         "output_tokens": 0, "timestamp": 0, "cached": True, "operation": "x"},
        {"model": "qwen3.6-plus", "elapsed": 4.0, "input_tokens": 1000,
         "output_tokens": 2000, "timestamp": 0, "cached": False,
         "operation": "x", "cost_usd": 0.0024},
    ])
    stats = get_call_stats(conn)
    plus = stats["by_model"]["qwen3.6-plus"]
    # live call is already in qwen_cache (choke point writes it): no double count
    assert plus["calls"] == 2
    assert plus["cached_calls"] == 1
    assert plus["avg_latency"] == 4.0
    assert stats["total_calls"] == 4  # 3 db live + 1 session cache hit


def test_fallback_to_memory_when_no_db():
    qwen._call_log.append(
        {"model": "qwen3.6-plus", "elapsed": 1.0, "input_tokens": 10,
         "output_tokens": 20, "timestamp": 0, "cached": False,
         "operation": "x", "cost_usd": 0.001}
    )
    stats = get_call_stats(None)
    assert stats["total_calls"] == 1
    assert stats["by_model"]["qwen3.6-plus"]["input_tokens"] == 10


def test_empty_everything():
    stats = get_call_stats(None)
    assert stats == {
        "total_calls": 0,
        "by_model": {},
        "cache": {"hits": 0, "misses": 0, "rate": 0.0, "entries": 0},
        "total_cost_usd": 0,
    }
