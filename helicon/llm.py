import hashlib
import json
import sqlite3
import sys
import time


def model_prices(config: dict | None) -> dict[str, tuple[float, float]]:
    """{model: (input, output)} in USD per MILLION tokens, from config
    `llm_prices`: {"<model id>": {"input": 0.25, "output": 1.0}}.

    Helicon ships no price table. A price belongs to an endpoint and a date,
    and only the person paying the bill knows it. A model with no entry here
    has an UNKNOWN cost, which is reported as None, never as a guess and never
    as 0. Entries that are not two non-negative numbers are dropped."""
    out: dict[str, tuple[float, float]] = {}
    raw = (config or {}).get("llm_prices")
    if not isinstance(raw, dict):
        return out
    for model, price in raw.items():
        if not isinstance(price, dict):
            continue
        pin, pout = price.get("input"), price.get("output")
        ok = all(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0
                 for v in (pin, pout))
        if ok:
            out[str(model)] = (float(pin), float(pout))
    return out


def call_cost(model: str, input_tokens: int, output_tokens: int,
              prices: dict | None) -> float | None:
    """USD for one call or one token sum, or None when the model has no
    configured price. None means unknown. It is not zero."""
    price = (prices or {}).get(model)
    if price is None:
        return None
    return ((input_tokens or 0) * price[0] + (output_tokens or 0) * price[1]) / 1_000_000


def _sum_costs(costs) -> float | None:
    """Sum, unless any part is unknown: a total with a hole in it is unknown."""
    costs = list(costs)
    if any(c is None for c in costs):
        return None
    return round(sum(costs), 6)


_call_log: list[dict] = []
_cache: dict[str, str] = {}
_cache_stats = {"hits": 0, "misses": 0}
_route_log: list[dict] = []


def _cache_key(system: str, user: str, model: str, temperature: float | None = None) -> str:
    # temperature is part of the key: a greedy verdict and a sampled one are not
    # interchangeable, and a cache that conflates them would serve the sampled
    # answer to the judge that asked for greedy.
    return hashlib.sha256(f"{model}:{temperature}:{system}:{user}".encode()).hexdigest()[:24]


TIERS = ("fast", "default", "deep")


def llm_status(config: dict | None) -> dict:
    """{enabled, reason, key_source, ...} with the key itself left out, so a
    caller can print why the model-judged features are on or off."""
    from helicon.config import resolve_llm
    status = resolve_llm(config)
    status.pop("api_key", None)
    return status


def get_client(config: dict):
    """An OpenAI-compatible client for whatever endpoint the config names, or
    None when the model layer is off. There is no default vendor: None is the
    answer for a config with no endpoint, and llm_status says why."""
    from helicon.config import resolve_llm
    r = resolve_llm(config)
    if not r["enabled"]:
        return None
    from openai import OpenAI
    # A local endpoint needs no key, but the SDK refuses an empty one.
    client = OpenAI(api_key=r["api_key"] or "not-needed", base_url=r["base_url"])
    # complete() has no config, so the configured models and prices ride on
    # the client.
    try:
        client._helicon_prices = model_prices(config)
        client._helicon_models = {t: resolve_model(t, config) for t in TIERS}
        # The second contradiction judge (pairing.pair_scan). Off unless the
        # config names one.
        client._helicon_models["judge2"] = (config or {}).get("llm_judge2_model") or None
    except Exception:
        pass
    return client


def resolve_model(tier: str, config: dict | None = None) -> str | None:
    """The configured model for a tier, or None when none is configured. It
    does not guess: a model name belongs to an endpoint, and only the config
    knows which endpoint this is."""
    from helicon.config import resolve_llm
    cfg = config or {}
    tiers = cfg.get("llm_models") or {}
    if tiers.get(tier):
        return tiers[tier]
    return resolve_llm(cfg)["model"] or None


def default_model(client, tier: str = "default") -> str | None:
    """The model get_client resolved for this client and tier. None for a
    client that did not come from get_client: pass `model` yourself then."""
    models = getattr(client, "_helicon_models", None)
    if not isinstance(models, dict):
        return None
    if tier == "judge2":
        return models.get("judge2")
    return models.get(tier) or models.get("default")


# Stored provenance labels (judged_by in battery results and audit details).
# New records carry the model id that judged, or "llm" when no id is known.
# Rows written by earlier versions carry a vendor name or "model", and they
# are never rewritten. So a reader asks "is this one of the labels that mean
# no model was involved" and treats everything else as model-judged: every
# old value, "llm", and any model id, with no list of names to keep current.
NOT_MODEL_JUDGED = frozenset({"", "deterministic", "probe", "human", "helicon"})


def judge_label(client, model: str | None = None) -> str:
    """What to store as judged_by for a verdict this client produced."""
    return model or default_model(client) or "llm"


def is_model_judged(label) -> bool:
    """True when a stored judged_by / actor label names a model verdict."""
    if not isinstance(label, str):
        return False
    return label.strip().lower() not in NOT_MODEL_JUDGED


_warned_no_model = False


def _model_not_configured(operation: str = ""):
    # stderr, never stdout, for the same reason as the quota line in complete().
    global _warned_no_model
    if _warned_no_model:
        return
    _warned_no_model = True
    what = f" for {operation}" if operation else ""
    print(f"[llm] model not configured{what}: set llm_model (or HELICON_LLM_MODEL), "
          "or pass model=. Skipping the model call.", file=sys.stderr)


def load_cache_from_db(conn: sqlite3.Connection):
    try:
        # A database from before the table was renamed keeps its rows.
        from helicon.db import migrate_llm_cache
        migrate_llm_cache(conn)
        conn.execute("""CREATE TABLE IF NOT EXISTS llm_cache (
            cache_key TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            operation TEXT DEFAULT '',
            response TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )""")
        conn.commit()
        rows = conn.execute("SELECT cache_key, response FROM llm_cache").fetchall()
        for row in rows:
            _cache[row["cache_key"]] = row["response"]
    except Exception:
        pass


def _save_to_cache_db(conn: sqlite3.Connection | None, key: str, model: str, operation: str, response: str, in_tok: int, out_tok: int):
    if conn is None:
        return
    try:
        conn.execute(
            "INSERT OR REPLACE INTO llm_cache (cache_key, model, operation, response, input_tokens, output_tokens, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key, model, operation, response, in_tok, out_tok, time.strftime("%Y-%m-%dT%H:%M:%S")),
        )
        conn.commit()
    except Exception:
        pass


_db_conn: sqlite3.Connection | None = None


def set_cache_db(conn: sqlite3.Connection):
    global _db_conn
    _db_conn = conn
    load_cache_from_db(conn)


def complete(client, system: str, user: str, model: str | None = None, operation: str = "",
             response_format: dict | None = None, enable_thinking: bool | None = None,
             temperature: float | None = None) -> str:
    """temperature=None leaves the model's default sampling alone (narration and
    synthesis want the warmth). Pass 0 for anything that JUDGES: a verdict that
    changes between two identical calls is not a verdict. Measured 2026-07-17 on
    the live store, the identity judge at default temperature called the same
    pair ('Machine is a content curation tool' vs 'Machine is the eval loop')
    clean on one run and contradicted on the next. The exam has already been
    burned once by a non-deterministic remote call (the reranker, 11/12/11 across
    three runs); it does not get to happen twice."""
    if client is None:
        return ""
    model = model or default_model(client)
    if not model:
        _model_not_configured(operation)
        return ""

    key = _cache_key(system, user, model, temperature)
    if key in _cache:
        _cache_stats["hits"] += 1
        _call_log.append({
            "model": model,
            "elapsed": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "timestamp": time.time(),
            "cached": True,
            "operation": operation,
        })
        return _cache[key]

    _cache_stats["misses"] += 1
    start = time.time()
    # Structured output: on some endpoints JSON mode / function-calling is only
    # valid with thinking OFF, and only on some models. Fall back to a plain call if
    # the endpoint rejects the extra args so existing callers never break.
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    if temperature is not None:
        kwargs["temperature"] = temperature
    extra_body: dict = {}
    if enable_thinking is not None:
        extra_body["enable_thinking"] = enable_thinking
    if extra_body:
        kwargs["extra_body"] = extra_body
    try:
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as fmt_err:
            if response_format is None and not extra_body:
                raise
            # endpoint doesn't support response_format/extra_body on this model
            response = client.chat.completions.create(
                model=model,
                messages=kwargs["messages"],
            )
            _ = fmt_err
        elapsed = time.time() - start
        result = response.choices[0].message.content
        usage = response.usage
        in_tok = usage.prompt_tokens if usage else 0
        out_tok = usage.completion_tokens if usage else 0

        _cache[key] = result
        _save_to_cache_db(_db_conn, key, model, operation, result, in_tok, out_tok)

        # None when no price is configured for this model: unknown, not zero.
        cost = call_cost(model, in_tok, out_tok, getattr(client, "_helicon_prices", None))
        cost = None if cost is None else round(cost, 6)
        _call_log.append({
            "model": model,
            "elapsed": round(elapsed, 2),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "timestamp": time.time(),
            "cached": False,
            "operation": operation,
            "cost_usd": cost,
        })

        _route_log.append({
            "model": model,
            "operation": operation,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "latency": round(elapsed, 2),
            "cost_usd": cost,
            "timestamp": time.time(),
        })

        return result
    except Exception as e:
        if "403" in str(e) or "AllocationQuota" in str(e):
            # stderr, never stdout: `report --llm --json > eval-latest.json`
            # redirects stdout into the baseline file, so a stdout warning here
            # lands INSIDE the JSON and the file parses as CSV. That is how 14
            # nights of "eval-latest.json is empty, unreadable" were filed.
            print(f"[llm] Quota exhausted, skipping: {str(e)[:80]}", file=sys.stderr)
            return ""
        raise


def complete_json(client, system: str, user: str, model: str | None = None, operation: str = "",
                  temperature: float | None = None) -> dict | list | None:
    # Structured output: some endpoints require the word "json" in a message
    # and thinking disabled for response_format json_object; complete() falls back cleanly
    # if the model/endpoint rejects it, and we still parse the prose either way.
    raw = complete(client, system + "\n\nRespond with ONLY valid JSON. No markdown, no explanation.", user, model,
                   operation=operation, response_format={"type": "json_object"}, enable_thinking=False,
                   temperature=temperature)
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def get_call_stats(conn: sqlite3.Connection | None = None,
                   config: dict | None = None) -> dict:
    """Token/cost stats for the dashboard.

    Durable usage (calls, tokens) comes from the llm_cache table, which
    every live model call in ANY process writes to. The in-process _call_log only
    ever sees this process's calls (CLI runs like `helicon report --llm` happen
    in other processes), so it is used only for session-local data the DB does
    not have: cache hits and latency. Falls back to _call_log-only accounting
    when no DB connection is available.

    Cost is tokens times the configured price (config `llm_prices`). A model
    with no price has cost_usd None and is named in `unpriced_models`, and
    then total_cost_usd is None too: a total that leaves a model out would be
    a made-up number.
    """
    conn = conn if conn is not None else _db_conn
    prices = model_prices(config)
    by_model: dict[str, dict] = {}
    by_operation: dict[str, dict] = {}
    if conn is not None:
        try:
            for r in conn.execute(
                "SELECT COALESCE(NULLIF(operation, ''), 'other') op, COUNT(*) n, "
                "SUM(COALESCE(input_tokens,0)+COALESCE(output_tokens,0)) tok "
                "FROM llm_cache GROUP BY op ORDER BY n DESC"
            ):
                by_operation[r["op"]] = {"calls": r["n"], "tokens": r["tok"] or 0}
        except sqlite3.Error:
            pass

    def _bucket(model: str) -> dict:
        return by_model.setdefault(model, {
            "calls": 0, "cached_calls": 0, "input_tokens": 0,
            "output_tokens": 0, "avg_latency": 0, "cost_usd": None,
        })

    db_ok = False
    if conn is not None:
        try:
            rows = conn.execute(
                "SELECT model, COUNT(*) AS calls, "
                "COALESCE(SUM(input_tokens), 0) AS in_tok, "
                "COALESCE(SUM(output_tokens), 0) AS out_tok "
                "FROM llm_cache GROUP BY model"
            ).fetchall()
            for r in rows:
                b = _bucket(r["model"])
                b["calls"] = r["calls"]
                b["input_tokens"] = r["in_tok"]
                b["output_tokens"] = r["out_tok"]
            db_ok = True
        except Exception:
            by_model = {}

    for call in _call_log:
        b = _bucket(call["model"])
        if call.get("cached"):
            b["cached_calls"] += 1
        elif not db_ok:
            # No DB: fall back to in-memory accounting for live calls.
            b["calls"] += 1
            b["input_tokens"] += call["input_tokens"]
            b["output_tokens"] += call["output_tokens"]

    for m, b in by_model.items():
        live_calls = [c for c in _call_log if c["model"] == m and not c.get("cached")]
        if live_calls:
            b["avg_latency"] = round(sum(c["elapsed"] for c in live_calls) / len(live_calls), 2)
        cost = call_cost(m, b["input_tokens"], b["output_tokens"], prices)
        b["cost_usd"] = None if cost is None else round(cost, 6)

    # Only a model that actually used tokens can leave a hole in the total.
    unpriced = sorted(m for m, b in by_model.items()
                      if b["cost_usd"] is None and (b["input_tokens"] or b["output_tokens"]))
    total_cost = None if unpriced else _sum_costs(
        b["cost_usd"] or 0.0 for b in by_model.values())
    cache_rate = _cache_stats["hits"] / max(_cache_stats["hits"] + _cache_stats["misses"], 1)
    return {
        "by_operation": by_operation,
        "total_calls": sum(b["calls"] + b["cached_calls"] for b in by_model.values()),
        "by_model": by_model,
        "cache": {**_cache_stats, "rate": round(cache_rate, 3), "entries": len(_cache)},
        "total_cost_usd": total_cost,
        "unpriced_models": unpriced,
    }


def get_route_stats() -> dict:
    """Per-operation usage for this process. total_cost is None for an
    operation with any call whose model has no configured price."""
    by_op = {}
    for r in _route_log:
        op = r["operation"] or "unknown"
        if op not in by_op:
            by_op[op] = {"calls": 0, "models_used": {}, "avg_latency": 0, "total_cost": 0, "total_tokens": 0}
        by_op[op]["calls"] += 1
        by_op[op]["total_tokens"] += r["input_tokens"] + r["output_tokens"]
        m = r["model"]
        if m not in by_op[op]["models_used"]:
            by_op[op]["models_used"][m] = 0
        by_op[op]["models_used"][m] += 1
    for op in by_op:
        op_calls = [r for r in _route_log if (r["operation"] or "unknown") == op]
        by_op[op]["avg_latency"] = round(sum(r["latency"] for r in op_calls) / len(op_calls), 2)
        by_op[op]["total_cost"] = _sum_costs(r.get("cost_usd") for r in op_calls)
    return {"operations": by_op}


def get_cache_stats_db(conn: sqlite3.Connection) -> dict:
    try:
        total = conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0]
        by_model = conn.execute(
            "SELECT model, COUNT(*) as cnt, SUM(input_tokens) as in_tok, SUM(output_tokens) as out_tok FROM llm_cache GROUP BY model"
        ).fetchall()
        by_op = conn.execute(
            "SELECT operation, COUNT(*) as cnt FROM llm_cache WHERE operation != '' GROUP BY operation"
        ).fetchall()
        tokens_saved = conn.execute(
            "SELECT SUM(input_tokens + output_tokens) FROM llm_cache"
        ).fetchone()[0] or 0
        return {
            "cached_responses": total,
            "tokens_saved_on_hits": tokens_saved * _cache_stats["hits"],
            "by_model": {r["model"]: {"cached": r["cnt"], "tokens": (r["in_tok"] or 0) + (r["out_tok"] or 0)} for r in by_model},
            "by_operation": {r["operation"]: r["cnt"] for r in by_op},
        }
    except Exception:
        return {"cached_responses": 0}


def summarize_cube(client, content: str, model: str | None = None) -> dict | None:
    return complete_json(
        client,
        "You are a memory audit system. Given content from an AI agent's output, extract structured metadata.",
        f"""Analyze this content and return JSON:
{{
  "title": "concise title (under 60 chars)",
  "summary": "1-2 sentence summary",
  "type": "one of: code, draft, decision, file_created, memory, session, project, idea",
  "confidence": 0.0-1.0 (how relevant/actionable is this now?),
  "tags": ["tag1", "tag2"]
}}

Content:
{content[:2000]}""",
        model,
        operation="summarize",
    )


def check_novelty(client, new_content: str, existing_summaries: list[str], model: str | None = None) -> dict | None:
    existing_text = "\n".join(f"- {s}" for s in existing_summaries[:10])
    return complete_json(
        client,
        "You are a novelty gate for a memory system. Decide if new content should be added, skipped, or merged.",
        f"""New item:
{new_content[:500]}

Existing items in memory:
{existing_text}

Return JSON:
{{
  "action": "ADD" | "NOOP" | "MERGE",
  "reason": "brief explanation",
  "merge_with": null or index number of existing item to merge with
}}""",
        model,
        operation="novelty_gate",
    )


def detect_contradictions(client, item_a: str, item_b: str, model: str | None = None,
                          audit_context: str = "", temperature: float | None = 0.0) -> dict | None:
    """Greedy by default: this is a judge, and a judge that answers differently on
    two identical calls cannot be an exam. See complete() for the measurement."""
    context_block = f"\n\nAudit context (past behavior and patterns):\n{audit_context}" if audit_context else ""
    return complete_json(
        client,
        f"You are a factual consistency checker for a memory system.{context_block}",
        f"""Do these two memory items contradict each other?

Item A:
{item_a[:500]}

Item B:
{item_b[:500]}

Return JSON:
{{
  "contradicts": true/false,
  "explanation": "what specifically conflicts, or why they're consistent",
  "severity": "critical" | "warning" | "info"
}}""",
        model,
        operation="contradiction_detect",
        temperature=temperature,
    )


def audit_pattern(client, pattern_desc: str, recent_data: str, model: str | None = None) -> dict | None:
    return complete_json(
        client,
        "You are a meta-memory auditor. Challenge stored patterns against fresh evidence.",
        f"""Stored pattern:
{pattern_desc}

Recent data (last 30 days):
{recent_data[:1500]}

Does this pattern still hold? Return JSON:
{{
  "still_valid": true/false,
  "confidence": 0.0-1.0,
  "evidence_for": "supporting evidence",
  "evidence_against": "contradicting evidence",
  "recommendation": "keep" | "update" | "prune",
  "updated_description": "if recommending update, what should the pattern say now"
}}""",
        model,
        operation="pattern_audit",
    )
