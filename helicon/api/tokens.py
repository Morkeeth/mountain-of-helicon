"""Helicon's own LLM call usage, reported honestly.

This endpoint used to be `/tokens/dashboard` and it returned four hardcoded
zeros: `total_cost_usd`, `cost_usd`, `cached_calls` and `avg_latency`. None of
those four is knowable from the table it reads. `llm_cache` has seven columns
and not one of them is a price, a latency or a cache-hit counter. So a reader
of that payload saw a 0 and could not tell it apart from a measured zero.

Four corrections, in the order they matter.

1. AN UNAVAILABLE NUMBER IS null, NOT 0. Every unknown value is null, carries a
   provenance marker of `unavailable`, and names the reason in
   `unavailable_because`. Nothing in this payload is a guess.

2. THE NAME NOW MATCHES THE POPULATION. `tokens` reads as agent token usage
   across Claude Code, Codex and Cursor. This never saw any of those. It reads
   `llm_cache`, which is Helicon's OWN judge and narration calls. The honest
   route is `/llm-calls/dashboard`. The old path still serves, marked
   deprecated, because silently moving a published route is its own dishonesty.

3. A CACHE ROW IS NOT A CALL. `llm_cache` is keyed on `cache_key`, so it holds
   one row per distinct prompt. `COUNT(*)` over it undercounts calls by exactly
   the number of cache hits, and nothing records those. The field is therefore
   `cached_responses`, which is what the count actually is. `total_calls` is
   gone rather than wrong.

4. A PRICE COMES FROM THE USER, OR THERE IS NO COST. Helicon ships no price
   table. With `llm_prices` in config (USD per million input and output tokens,
   per model) the cost of a model's cached responses is its measured token
   sums times that price, marked `derived`. A model with no configured price
   has a null cost and is named in `unpriced_models`, and then the total is
   null too.

The real usage question, tokens across the harnesses, needs a source this
endpoint has never had.
"""
import sqlite3

from fastapi import APIRouter

from helicon.api.app import get_config, get_conn
from helicon.llm import call_cost, model_prices

router = APIRouter()

SOURCE = "llm_cache (helicon.db)"
POPULATION = "helicon_own_llm_calls"
HONEST_PATH = "/api/llm-calls/dashboard"

# Every number in the payload appears here. A field with no marker is a field
# that can quietly become a guess, so the tests assert this map is complete.
# The two cost markers are the no-price default; _payload flips them to
# `derived` when a configured price produced the number.
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

_NO_PRICE = ("llm_cache stores no price and Helicon ships no price table. Set "
             "llm_prices in config (USD per million input and output tokens, "
             "per model) to get a cost.")

UNAVAILABLE_BECAUSE = {
    "total_cost_usd": _NO_PRICE,
    "cost_usd": _NO_PRICE,
    "avg_latency": "llm_cache has no latency column. Call duration is not "
                   "recorded anywhere in this store.",
    "cached_calls": "llm_cache is keyed on cache_key, so it records distinct "
                    "cached responses. Cache HITS are not counted, so the "
                    "number of calls those responses served is unknown.",
}


def _dashboard() -> dict:
    conn = get_conn()
    prices = model_prices(get_config())
    try:
        rows = conn.execute(
            "SELECT model, COUNT(*) AS cached_responses, "
            "SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens "
            "FROM llm_cache GROUP BY model"
        ).fetchall()
    except sqlite3.OperationalError:
        # No table is not an empty table. Say which one it is.
        return _payload([], store_present=False, prices=prices)
    return _payload(rows, store_present=True, prices=prices)


def _payload(rows, store_present: bool, prices: dict | None = None) -> dict:
    by_model = {}
    total_cached = 0
    total_tokens = 0
    unpriced = []
    for r in rows:
        inp = r["input_tokens"] or 0
        out = r["output_tokens"] or 0
        cost = call_cost(r["model"], inp, out, prices)
        if cost is None:
            unpriced.append(r["model"])
        by_model[r["model"]] = {
            "cached_responses": r["cached_responses"],
            "input_tokens": inp,
            "output_tokens": out,
            # Derived from the configured price, or null. Never 0, never a guess.
            "cost_usd": None if cost is None else round(cost, 6),
            # The two this source cannot supply. null, never 0.
            "avg_latency": None,
            "cached_calls": None,
        }
        total_cached += r["cached_responses"]
        total_tokens += inp + out

    priced = [m for m in by_model if m not in unpriced]
    # A total with one model left out is not the total.
    total_cost = (round(sum(by_model[m]["cost_usd"] for m in priced), 6)
                  if priced and not unpriced else None)
    provenance = dict(PROVENANCE)
    because = dict(UNAVAILABLE_BECAUSE)
    if priced:
        provenance["cost_usd"] = "derived"
        if unpriced:
            because["cost_usd"] = ("null for a model with no entry in llm_prices: "
                                   + ", ".join(sorted(unpriced)) + ".")
        else:
            because.pop("cost_usd")
    if total_cost is not None:
        provenance["total_cost_usd"] = "derived"
        because.pop("total_cost_usd")
    elif priced:
        because["total_cost_usd"] = ("no entry in llm_prices for: "
                                     + ", ".join(sorted(unpriced))
                                     + ". A total that leaves a model out is not a total.")

    return {
        "population": POPULATION,
        "source": SOURCE,
        "store_present": store_present,
        "total_cached_responses": total_cached,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "unpriced_models": sorted(unpriced),
        "by_model": by_model,
        "provenance": provenance,
        "unavailable_because": because,
    }


@router.get("/llm-calls/dashboard")
async def llm_calls_dashboard():
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
