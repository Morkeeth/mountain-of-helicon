from fastapi import APIRouter

from glaze.api.app import get_conn
from glaze.triage import run_auto_triage, get_triage_stats, get_triage_rules

router = APIRouter()


@router.post("/triage/run")
async def triage_run(dry_run: bool = False):
    conn = get_conn()
    result = run_auto_triage(conn, dry_run=dry_run)
    return result


@router.get("/triage/stats")
async def triage_stats():
    conn = get_conn()
    return get_triage_stats(conn)


@router.get("/triage/rules")
async def triage_rules():
    conn = get_conn()
    rules = get_triage_rules(conn)
    return {"rules": rules, "total": len(rules)}
