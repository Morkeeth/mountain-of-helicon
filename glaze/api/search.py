from fastapi import APIRouter, Query

from glaze.api.app import get_conn, get_config
from glaze.db import search_cubes, rebuild_fts
from glaze.consolidation import find_clusters, run_consolidation, get_consolidations
from glaze.qwen import get_client

router = APIRouter()


@router.get("/search")
async def search(q: str = Query(..., min_length=1), limit: int = 30):
    conn = get_conn()
    try:
        results = search_cubes(conn, q, limit)
        return {"results": results, "total": len(results), "query": q}
    except Exception as e:
        return {"results": [], "total": 0, "query": q, "error": str(e)}


@router.post("/search/rebuild")
async def rebuild_index():
    conn = get_conn()
    rebuild_fts(conn)
    return {"status": "rebuilt"}


@router.get("/consolidations")
async def list_consolidations():
    conn = get_conn()
    return {"consolidations": get_consolidations(conn)}


@router.get("/consolidations/clusters")
async def list_clusters():
    conn = get_conn()
    clusters = find_clusters(conn)
    return {"clusters": clusters}


@router.post("/consolidations/run")
async def trigger_consolidation(use_qwen: bool = False, max_clusters: int = 10):
    conn = get_conn()
    config = get_config()
    qwen_client = get_client(config) if use_qwen else None
    result = run_consolidation(conn, qwen_client, max_clusters)
    return result
