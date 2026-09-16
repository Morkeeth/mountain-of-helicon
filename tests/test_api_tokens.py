"""The token surface may not invent a number, and may not mislabel the one it has.

Two separate defects live in the same endpoint, and both are the wrong-object
failure rather than an arithmetic failure.

1. UNKNOWN RENDERED AS ZERO. `cost_usd`, `total_cost_usd`, `cached_calls` and
   `avg_latency` were hardcoded literal 0. The `qwen_cache` table carries no
   price column, no latency column and no cache-hit counter, so none of those
   four numbers is knowable from this source. A 0 cannot be told apart from a
   measured zero by any reader, so the value must be null and must carry a
   provenance marker saying it is unavailable.

2. THE NAME ANSWERS A DIFFERENT QUESTION. The route was `/tokens/dashboard`,
   which reads as agent token usage across the harnesses. It reads `qwen_cache`,
   which is Helicon's OWN judge calls. Those are different populations. The
   route now says what it reads.

There is a third, quieter one that this test also pins. `qwen_cache` has
`cache_key` as its PRIMARY KEY, so it holds one row per distinct prompt, not
one row per call. `COUNT(*)` over it is the number of cached responses, and it
undercounts calls by exactly the number of cache hits, which nothing records.
So the field is named for what it is.
"""
import pytest

# helicon.api.app MUST be imported before any router module, see test_api_rot.py.
import helicon.api.app  # noqa: F401  (import order is load-bearing)


def _client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from helicon.api import app as app_mod
    monkeypatch.setattr(app_mod, "load_config",
                        lambda: {"db_path": str(tmp_path / "api.db")})
    return TestClient(app_mod.create_app())


def _seed(tmp_path, rows=None):
    """Two distinct cached responses for one model, with real token counts.

    Seeded against the db FILE before the app opens it. The app holds one
    sqlite connection bound to the startup thread, and TestClient runs the
    request on another, so reaching for `get_conn()` inside a test raises
    ProgrammingError rather than testing anything.
    """
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "api.db"))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS qwen_cache ("
        "cache_key TEXT PRIMARY KEY, model TEXT NOT NULL, operation TEXT DEFAULT '',"
        "response TEXT NOT NULL, input_tokens INTEGER DEFAULT 0,"
        "output_tokens INTEGER DEFAULT 0, created_at TEXT NOT NULL)")
    conn.executemany(
        "INSERT OR REPLACE INTO qwen_cache"
        "(cache_key, model, response, input_tokens, output_tokens, created_at)"
        " VALUES (?,?,?,?,?,?)",
        rows if rows is not None else
        [("k1", "qwen-max", "{}", 100, 10, "2026-09-16T00:00:00Z"),
         ("k2", "qwen-max", "{}", 200, 20, "2026-09-16T00:01:00Z")])
    conn.commit()
    conn.close()


# --- defect 1: unknown must never render as zero ----------------------------

UNKNOWABLE = ("cost_usd", "avg_latency", "cached_calls")


def test_unknown_numbers_are_null_not_zero(tmp_path, monkeypatch):
    """The four numbers this source cannot supply must be null, not 0.

    This is the check that goes red against the shipped code, where all four
    were the integer literal 0.
    """
    _seed(tmp_path)
    with _client(tmp_path, monkeypatch) as c:
        body = c.get("/api/qwen-calls/dashboard").json()

        assert body["total_cost_usd"] is None, \
            "a dollar total this source cannot know must be null, not 0"
        for model, row in body["by_model"].items():
            for field in UNKNOWABLE:
                assert row[field] is None, \
                    f"{model}.{field} is not knowable from qwen_cache; it must be null"


def test_every_number_carries_a_provenance_marker(tmp_path, monkeypatch):
    """A schema that permits an unmarked number will eventually hold a guess.

    Every numeric field in the payload must appear in `provenance`, and every
    marker must be one of the three allowed values.
    """
    _seed(tmp_path)
    with _client(tmp_path, monkeypatch) as c:
        body = c.get("/api/qwen-calls/dashboard").json()

        prov = body["provenance"]
        assert set(prov.values()) <= {"measured", "derived", "unavailable"}

        numeric_top = [k for k, v in body.items()
                       if isinstance(v, (int, float)) or
                       (v is None and k != "by_model")]
        for field in numeric_top:
            assert field in prov, f"top-level `{field}` has no provenance marker"

        for row in body["by_model"].values():
            for field in row:
                assert field in prov, f"per-model `{field}` has no provenance marker"

        for field in UNKNOWABLE:
            assert prov[field] == "unavailable"
        assert prov["input_tokens"] == "measured"
        assert prov["output_tokens"] == "measured"


def test_unavailable_fields_say_why(tmp_path, monkeypatch):
    """An unavailable number with no reason is just a hole. Name the reason."""
    _seed(tmp_path)
    with _client(tmp_path, monkeypatch) as c:
        body = c.get("/api/qwen-calls/dashboard").json()
        for field in UNKNOWABLE + ("total_cost_usd",):
            assert body["unavailable_because"][field].strip(), \
                f"`{field}` is unavailable but the payload does not say why"


# --- defect 2: the name must match the question -----------------------------

def test_the_payload_names_the_population_it_read(tmp_path, monkeypatch):
    """A reader must not be able to mistake Helicon's own judge calls for the
    agent token usage across Claude Code, Codex and Cursor. Those are different
    populations and this endpoint only ever saw one of them."""
    _seed(tmp_path)
    with _client(tmp_path, monkeypatch) as c:
        body = c.get("/api/qwen-calls/dashboard").json()
        assert body["population"] == "helicon_own_llm_calls"
        assert "qwen_cache" in body["source"]


def test_old_route_still_serves_the_honest_payload(tmp_path, monkeypatch):
    """Renaming a published route silently is its own dishonesty. The old path
    keeps working and returns the same honest body, marked deprecated."""
    _seed(tmp_path)
    with _client(tmp_path, monkeypatch) as c:
        old = c.get("/api/tokens/dashboard").json()
        new = c.get("/api/qwen-calls/dashboard").json()
        assert old["deprecated_alias_for"] == "/api/qwen-calls/dashboard"
        for key in ("total_cost_usd", "by_model", "population", "provenance"):
            assert old[key] == new[key]


# --- defect 3: count the object you actually have ---------------------------

def test_cached_responses_is_not_called_calls(tmp_path, monkeypatch):
    """`qwen_cache` is keyed on cache_key, so a row is a distinct prompt, not a
    call. Two seeded rows are two cached responses. The number of CALLS that
    produced them is not recorded anywhere, so it must not be reported."""
    _seed(tmp_path)
    with _client(tmp_path, monkeypatch) as c:
        body = c.get("/api/qwen-calls/dashboard").json()

        assert body["total_cached_responses"] == 2
        assert body["by_model"]["qwen-max"]["cached_responses"] == 2
        assert "calls" not in body["by_model"]["qwen-max"], \
            "a cache row is not a call; do not name it one"
        assert "total_calls" not in body


def test_measured_totals_are_still_right(tmp_path, monkeypatch):
    """Honesty about the unknown must not cost the numbers that ARE known."""
    _seed(tmp_path)
    with _client(tmp_path, monkeypatch) as c:
        body = c.get("/api/qwen-calls/dashboard").json()
        assert body["total_tokens"] == 330
        row = body["by_model"]["qwen-max"]
        assert row["input_tokens"] == 300
        assert row["output_tokens"] == 30


def test_empty_store_is_empty_not_zero_dollars(tmp_path, monkeypatch):
    """A store with no rows has no measured tokens. It still has no dollars,
    and the dollar figure stays null rather than becoming a truthful-looking 0."""
    _seed(tmp_path, rows=[])
    with _client(tmp_path, monkeypatch) as c:
        body = c.get("/api/qwen-calls/dashboard").json()
        assert body["total_cached_responses"] == 0
        assert body["total_tokens"] == 0
        assert body["total_cost_usd"] is None
        assert body["by_model"] == {}
