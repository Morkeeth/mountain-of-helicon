import hashlib
import json
import sqlite3
import time

MODELS = {
    "fast": "qwen3.6-flash",
    "default": "qwen3.6-plus",
    "deep": "qwen3.7-max",
}

TIER_COST_PER_1K = {
    "qwen-turbo": 0.0003,
    "qwen-plus": 0.0008,
    "qwen-max": 0.0024,
}

_call_log: list[dict] = []
_cache: dict[str, str] = {}
_cache_stats = {"hits": 0, "misses": 0}
_route_log: list[dict] = []


def _cache_key(system: str, user: str, model: str) -> str:
    return hashlib.sha256(f"{model}:{system}:{user}".encode()).hexdigest()[:24]


def get_client(config: dict):
    api_key = config.get("qwen_api_key", "")
    if not api_key:
        return None
    from openai import OpenAI
    return OpenAI(
        api_key=api_key,
        base_url=config.get("qwen_base_url", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
    )


def resolve_model(tier: str, config: dict | None = None) -> str:
    if config and "qwen_models" in config:
        return config["qwen_models"].get(tier, MODELS.get(tier, "qwen-plus"))
    return MODELS.get(tier, "qwen-plus")


def load_cache_from_db(conn: sqlite3.Connection):
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS qwen_cache (
            cache_key TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            operation TEXT DEFAULT '',
            response TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )""")
        conn.commit()
        rows = conn.execute("SELECT cache_key, response FROM qwen_cache").fetchall()
        for row in rows:
            _cache[row["cache_key"]] = row["response"]
    except Exception:
        pass


def _save_to_cache_db(conn: sqlite3.Connection | None, key: str, model: str, operation: str, response: str, in_tok: int, out_tok: int):
    if conn is None:
        return
    try:
        conn.execute(
            "INSERT OR REPLACE INTO qwen_cache (cache_key, model, operation, response, input_tokens, output_tokens, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
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


def complete(client, system: str, user: str, model: str = "qwen3.6-plus", operation: str = "") -> str:
    if client is None:
        return ""

    key = _cache_key(system, user, model)
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
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        elapsed = time.time() - start
        result = response.choices[0].message.content
        usage = response.usage
        in_tok = usage.prompt_tokens if usage else 0
        out_tok = usage.completion_tokens if usage else 0

        _cache[key] = result
        _save_to_cache_db(_db_conn, key, model, operation, result, in_tok, out_tok)

        cost = (in_tok + out_tok) / 1000 * TIER_COST_PER_1K.get(model, 0.001)
        _call_log.append({
            "model": model,
            "elapsed": round(elapsed, 2),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "timestamp": time.time(),
            "cached": False,
            "operation": operation,
            "cost_usd": round(cost, 6),
        })

        _route_log.append({
            "model": model,
            "operation": operation,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "latency": round(elapsed, 2),
            "cost_usd": round(cost, 6),
            "timestamp": time.time(),
        })

        return result
    except Exception as e:
        if "403" in str(e) or "AllocationQuota" in str(e):
            print(f"[qwen] Quota exhausted, skipping: {str(e)[:80]}")
            return ""
        raise


def complete_json(client, system: str, user: str, model: str = "qwen3.6-plus", operation: str = "") -> dict | list | None:
    raw = complete(client, system + "\n\nRespond with ONLY valid JSON. No markdown, no explanation.", user, model, operation=operation)
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def get_call_stats() -> dict:
    if not _call_log:
        return {"total_calls": 0, "by_model": {}, "cache": _cache_stats, "total_cost_usd": 0}
    by_model = {}
    total_cost = 0
    for call in _call_log:
        m = call["model"]
        if m not in by_model:
            by_model[m] = {"calls": 0, "cached_calls": 0, "input_tokens": 0, "output_tokens": 0, "avg_latency": 0, "cost_usd": 0}
        by_model[m]["calls"] += 1
        if call.get("cached"):
            by_model[m]["cached_calls"] += 1
        by_model[m]["input_tokens"] += call["input_tokens"]
        by_model[m]["output_tokens"] += call["output_tokens"]
        by_model[m]["cost_usd"] += call.get("cost_usd", 0)
        total_cost += call.get("cost_usd", 0)
    for m in by_model:
        live_calls = [c for c in _call_log if c["model"] == m and not c.get("cached")]
        by_model[m]["avg_latency"] = round(sum(c["elapsed"] for c in live_calls) / max(len(live_calls), 1), 2)
        by_model[m]["cost_usd"] = round(by_model[m]["cost_usd"], 6)
    cache_rate = _cache_stats["hits"] / max(_cache_stats["hits"] + _cache_stats["misses"], 1)
    return {
        "total_calls": len(_call_log),
        "by_model": by_model,
        "cache": {**_cache_stats, "rate": round(cache_rate, 3), "entries": len(_cache)},
        "total_cost_usd": round(total_cost, 6),
    }


def get_route_stats() -> dict:
    if not _route_log:
        return {"operations": {}, "recommendations": []}
    by_op = {}
    for r in _route_log:
        op = r["operation"] or "unknown"
        if op not in by_op:
            by_op[op] = {"calls": 0, "models_used": {}, "avg_latency": 0, "total_cost": 0, "total_tokens": 0}
        by_op[op]["calls"] += 1
        by_op[op]["total_cost"] += r["cost_usd"]
        by_op[op]["total_tokens"] += r["input_tokens"] + r["output_tokens"]
        m = r["model"]
        if m not in by_op[op]["models_used"]:
            by_op[op]["models_used"][m] = 0
        by_op[op]["models_used"][m] += 1
    for op in by_op:
        op_calls = [r for r in _route_log if (r["operation"] or "unknown") == op]
        by_op[op]["avg_latency"] = round(sum(r["latency"] for r in op_calls) / len(op_calls), 2)
        by_op[op]["total_cost"] = round(by_op[op]["total_cost"], 6)

    recommendations = []
    for op, stats in by_op.items():
        if stats["calls"] >= 3:
            models = stats["models_used"]
            if any(m in models for m in ("qwen-max", "qwen-plus")) and stats["avg_latency"] < 2.0:
                cheaper = "qwen-turbo" if "qwen-max" in models or "qwen-plus" in models else None
                if cheaper:
                    savings = stats["total_cost"] * 0.6
                    recommendations.append({
                        "operation": op,
                        "current_model": max(models, key=models.get),
                        "suggested": cheaper,
                        "reason": f"Low latency ({stats['avg_latency']}s) suggests {cheaper} may suffice",
                        "estimated_savings_usd": round(savings, 6),
                    })

    return {"operations": by_op, "recommendations": recommendations}


def get_cache_stats_db(conn: sqlite3.Connection) -> dict:
    try:
        total = conn.execute("SELECT COUNT(*) FROM qwen_cache").fetchone()[0]
        by_model = conn.execute(
            "SELECT model, COUNT(*) as cnt, SUM(input_tokens) as in_tok, SUM(output_tokens) as out_tok FROM qwen_cache GROUP BY model"
        ).fetchall()
        by_op = conn.execute(
            "SELECT operation, COUNT(*) as cnt FROM qwen_cache WHERE operation != '' GROUP BY operation"
        ).fetchall()
        tokens_saved = conn.execute(
            "SELECT SUM(input_tokens + output_tokens) FROM qwen_cache"
        ).fetchone()[0] or 0
        return {
            "cached_responses": total,
            "tokens_saved_on_hits": tokens_saved * _cache_stats["hits"],
            "by_model": {r["model"]: {"cached": r["cnt"], "tokens": (r["in_tok"] or 0) + (r["out_tok"] or 0)} for r in by_model},
            "by_operation": {r["operation"]: r["cnt"] for r in by_op},
        }
    except Exception:
        return {"cached_responses": 0}


def summarize_cube(client, content: str, model: str = "qwen3.6-plus") -> dict | None:
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


def check_novelty(client, new_content: str, existing_summaries: list[str], model: str = "qwen3.6-plus") -> dict | None:
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


def detect_contradictions(client, item_a: str, item_b: str, model: str = "qwen3.6-plus", audit_context: str = "") -> dict | None:
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
    )


def audit_pattern(client, pattern_desc: str, recent_data: str, model: str = "qwen3.6-plus") -> dict | None:
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
