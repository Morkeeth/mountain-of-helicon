"""Helicon's own LLM call usage, reported honestly.

This endpoint used to be `/tokens/dashboard` and it returned four hardcoded
zeros: `total_cost_usd`, `cost_usd`, `cached_calls` and `avg_latency`. None of
those four is knowable from the table it reads. `qwen_cache` has seven columns
and not one of them is a price, a latency or a cache-hit counter. So a reader
of that payload saw a 0 and could not tell it apart from a measured zero.

Three corrections, in the order they matter.

1. AN UNAVAILABLE NUMBER IS null, NOT 0. Every unknown value is null, carries a
   provenance marker of `unavailable`, and names the reason in
   `unavailable_because`. Nothing in this payload is a guess.

2. THE NAME NOW MATCHES THE POPULATION. `tokens` reads as agent token usage
   across Claude Code, Codex and Cursor. This never saw any of those. It reads
   `qwen_cache`, which is Helicon's OWN judge and narration calls. The honest
   route is `/qwen-calls/dashboard`. The old path still serves, marked
   deprecated, because silently moving a published route is its own dishonesty.

3. A CACHE ROW IS NOT A CALL. `qwen_cache` is keyed on `cache_key`, so it holds
   one row per distinct prompt. `COUNT(*)` over it undercounts calls by exactly
   the number of cache hits, and nothing records those. The field is therefore
   `cached_responses`, which is what the count actually is. `total_calls` is
   gone rather than wrong.

What is left after all of that is two token sums and a response count. That is
the correct outcome and it is also the argument for the shared core: the real
usage question, tokens across the harnesses, needs a source this endpoint has
never had.
"""
import sqlite3

from fastapi import APIRouter

from helicon.api.app import get_conn

router = APIRouter()

SOURCE = "qwen_cache (helicon.db)"
POPULATION = "helicon_own_llm_calls"
HONEST_PATH = "/api/qwen-calls/dashboard"

# Every number in the payload appears here. A field with no marker is a field
# that can quietly become a guess, so the tests assert this map is complete.
PROVENANCE = {
    "store_present": "measured",
    "total_cached_responses": "measured",
    "total_tokens": "measured",
    "total_cost_usd": "unavailable",
    "cached_responses": "measured",
    "input_tokens": "measured",
    "output_tokens": "measured",
    "cost_usd": "unavailable",
    "avg_latency": "unavailable",
    "cached_calls": "unavailable",
}

UNAVAILABLE_BECAUSE = {
    "total_cost_usd": "qwen_cache stores no price and the Qwen key is BYOK, so "
                      "there is no per call cost to read or derive.",
    "cost_usd": "qwen_cache stores no price and the Qwen key is BYOK, so there "
                "is no per call cost to read or derive.",
    "avg_latency": "qwen_cache has no latency column. Call duration is not "
                   "recorded anywhere in this store.",
    "cached_calls": "qwen_cache is keyed on cache_key, so it records distinct "
                    "cached responses. Cache HITS are not counted, so the "
                    "number of calls those responses served is unknown.",
}


def _dashboard() -> dict:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT model, COUNT(*) AS cached_responses, "
            "SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens "
            "FROM qwen_cache GROUP BY model"
        ).fetchall()
    except sqlite3.OperationalError:
        # No table is not an empty table. Say which one it is.
        return _payload([], store_present=False)
    return _payload(rows, store_present=True)


def _payload(rows, store_present: bool) -> dict:
    by_model = {}
    total_cached = 0
    total_tokens = 0
    for r in rows:
        inp = r["input_tokens"] or 0
        out = r["output_tokens"] or 0
        by_model[r["model"]] = {
            "cached_responses": r["cached_responses"],
            "input_tokens": inp,
            "output_tokens": out,
            # The three this source cannot supply. null, never 0.
            "cost_usd": None,
            "avg_latency": None,
            "cached_calls": None,
        }
        total_cached += r["cached_responses"]
        total_tokens += inp + out

    return {
        "population": POPULATION,
        "source": SOURCE,
        "store_present": store_present,
        "total_cached_responses": total_cached,
        "total_tokens": total_tokens,
        "total_cost_usd": None,
        "by_model": by_model,
        "provenance": PROVENANCE,
        "unavailable_because": UNAVAILABLE_BECAUSE,
    }


@router.get("/qwen-calls/dashboard")
async def qwen_calls_dashboard():
    return _dashboard()


@router.get("/tokens/dashboard")
async def token_dashboard_deprecated():
    """The old path. It answers the same question and says where it moved.

    It is kept because a published route that starts 404ing is a worse failure
    than a route with a misleading name, and because the payload itself now
    states the population it read.
    """
    body = _dashboard()
    body["deprecated_alias_for"] = HONEST_PATH
    body["deprecation_note"] = (
        "This path is named `tokens` but reads Helicon's own LLM calls, not "
        "agent token usage across harnesses. Use " + HONEST_PATH + "."
    )
    return body
