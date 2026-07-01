import json
from fastapi import APIRouter

from glaze.api.app import get_conn, get_config
from glaze.score import compute_score, get_score_history, backfill_score_history, record_score_snapshot
from glaze.forgetting import apply_decay, get_decay_stats
from glaze.qwen import get_client as _get_client, get_call_stats, get_route_stats, get_cache_stats_db, MODELS, TIER_COST_PER_1K

router = APIRouter()


@router.get("/score")
async def get_score():
    conn = get_conn()
    return compute_score(conn)


@router.post("/decay")
async def run_decay():
    conn = get_conn()
    config = get_config()
    stats = apply_decay(conn, config)
    return stats


@router.get("/decay/stats")
async def decay_stats():
    conn = get_conn()
    return get_decay_stats(conn)


@router.get("/timeline")
async def timeline():
    conn = get_conn()
    rows = conn.execute("""
        SELECT date(created_at) as day,
               COUNT(*) as added,
               AVG(confidence) as avg_conf,
               source
        FROM glaze_cubes
        GROUP BY day, source
        ORDER BY day
    """).fetchall()

    review_rows = conn.execute("""
        SELECT date(reviewed_at) as day,
               decision,
               COUNT(*) as count
        FROM reviews
        GROUP BY day, decision
        ORDER BY day
    """).fetchall()

    return {
        "ingestion": [dict(r) for r in rows],
        "reviews": [dict(r) for r in review_rows],
    }


@router.get("/report")
async def health_report():
    conn = get_conn()
    config = get_config()

    score = compute_score(conn)
    decay = get_decay_stats(conn)

    audit_stats = conn.execute("""
        SELECT severity, COUNT(*) as cnt
        FROM audit_log
        WHERE human_decision IS NULL
        GROUP BY severity
    """).fetchall()

    pattern_count = conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]

    oldest = conn.execute("""
        SELECT title, created_at, confidence
        FROM glaze_cubes
        WHERE review_status = 'pending'
        ORDER BY confidence ASC LIMIT 3
    """).fetchall()

    context = {
        "score": score["score"],
        "total": score["total"],
        "reviewed": score["reviewed"],
        "pending": score["pending"],
        "audit_log": {s["severity"]: s["cnt"] for s in audit_stats},
        "patterns_learned": pattern_count,
        "decay_by_type": {k: {"avg": round(v["avg_confidence"], 3), "count": v["count"]} for k, v in decay.items()},
        "most_decayed": [{"title": r["title"], "confidence": round(r["confidence"], 4)} for r in oldest],
    }

    try:
        client = _get_client(config)
        resp = client.chat.completions.create(
            model=config.get("qwen_model", "qwen-plus"),
            messages=[
                {"role": "system", "content": "You are a memory health analyst. Given memory system statistics, write a concise 3-paragraph health report. Be specific about numbers. Use plain language. No markdown headers."},
                {"role": "user", "content": f"Generate a health report for this memory system:\n{json.dumps(context, indent=2)}"}
            ],
            temperature=0.3,
        )
        report_text = resp.choices[0].message.content
    except Exception:
        report_text = None

    return {
        "stats": context,
        "report": report_text,
    }


@router.get("/score/history")
async def score_history():
    conn = get_conn()
    return {"history": get_score_history(conn)}


@router.post("/score/history/backfill")
async def score_history_backfill():
    conn = get_conn()
    return backfill_score_history(conn)


@router.post("/score/snapshot")
async def score_snapshot(event_label: str = None):
    conn = get_conn()
    record_score_snapshot(conn, event_label)
    return {"status": "recorded"}


@router.get("/qwen/stats")
async def qwen_stats():
    stats = get_call_stats()
    return stats


@router.get("/qwen/models")
async def qwen_models():
    config = get_config()
    custom = config.get("qwen_models", {})
    return {
        "routing": {
            "fast": custom.get("fast", MODELS["fast"]),
            "default": custom.get("default", MODELS["default"]),
            "deep": custom.get("deep", MODELS["deep"]),
        },
        "cost_per_1k_tokens": TIER_COST_PER_1K,
        "usage": {
            "fast": "Novelty gate (ADD/NOOP/MERGE), summarization, tag extraction",
            "default": "Pattern detection, health reports, entity extraction",
            "deep": "Audit passes, contradiction detection, consolidation synthesis",
        },
    }


@router.get("/qwen/cache")
async def qwen_cache():
    conn = get_conn()
    return get_cache_stats_db(conn)


@router.get("/qwen/routing")
async def qwen_routing():
    return get_route_stats()
