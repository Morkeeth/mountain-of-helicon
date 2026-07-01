from fastapi import APIRouter

from glaze.api.app import get_conn

router = APIRouter()


@router.get("/tokens/dashboard")
async def token_dashboard():
    conn = get_conn()
    rows = conn.execute(
        "SELECT model, COUNT(*) as calls, "
        "SUM(input_tokens) as input_tokens, SUM(output_tokens) as output_tokens "
        "FROM qwen_cache GROUP BY model"
    ).fetchall()

    by_model = {}
    total_calls = 0
    total_tokens = 0
    for r in rows:
        by_model[r["model"]] = {
            "calls": r["calls"],
            "cached_calls": 0,
            "input_tokens": r["input_tokens"] or 0,
            "output_tokens": r["output_tokens"] or 0,
            "avg_latency": 0,
            "cost_usd": 0,
        }
        total_calls += r["calls"]
        total_tokens += (r["input_tokens"] or 0) + (r["output_tokens"] or 0)

    return {
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "total_cost_usd": 0,
        "by_model": by_model,
    }
