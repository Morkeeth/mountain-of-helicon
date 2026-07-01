from fastapi import APIRouter

from glaze.api.app import get_conn, get_config
from glaze.db import get_patterns
from glaze.patterns import (
    extract_patterns_from_sql,
    extract_patterns_with_qwen,
    save_patterns,
    detect_spin,
    detect_kill_candidates,
    compute_shipping_rates,
)
from glaze.qwen import get_client as _get_client

router = APIRouter()


@router.get("/patterns")
async def list_patterns():
    conn = get_conn()
    return {"patterns": get_patterns(conn)}


@router.post("/patterns/extract")
async def extract():
    conn = get_conn()
    client = _get_client(get_config())
    if client:
        patterns = extract_patterns_with_qwen(conn, client)
    else:
        patterns = extract_patterns_from_sql(conn)
    save_patterns(conn, patterns)
    return {"extracted": len(patterns), "patterns": [{"name": p.name, "description": p.description} for p in patterns]}


@router.get("/patterns/spin")
async def spin():
    conn = get_conn()
    return {"spins": detect_spin(conn)}


@router.get("/patterns/kill-candidates")
async def kill_candidates():
    conn = get_conn()
    return {"candidates": detect_kill_candidates(conn)}


@router.get("/patterns/shipping-rates")
async def shipping_rates():
    conn = get_conn()
    return {"rates": compute_shipping_rates(conn)}
