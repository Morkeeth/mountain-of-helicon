from fastapi import APIRouter, Query

from glaze.api.app import get_conn, get_config
from glaze.db import get_cubes
from glaze.scanner import run_scan

router = APIRouter()


@router.get("/cubes")
async def list_cubes(
    status: str | None = None,
    source: str | None = None,
    type: str | None = None,
    sort: str = "urgency",
    limit: int = Query(default=50, le=200),
    offset: int = 0,
):
    conn = get_conn()
    cubes, total = get_cubes(conn, status=status, source=source, cube_type=type, sort=sort, limit=limit, offset=offset)
    return {"cubes": cubes, "total": total, "limit": limit, "offset": offset}


@router.get("/cubes/{cube_id}")
async def get_cube(cube_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM glaze_cubes WHERE id = ?", (cube_id,)).fetchone()
    if not row:
        return {"error": "not found"}, 404
    import json
    cube = dict(row)
    cube["tags"] = json.loads(cube["tags"]) if cube["tags"] else []
    cube["metadata"] = json.loads(cube["metadata"]) if cube["metadata"] else {}
    return cube


@router.post("/scan")
async def trigger_scan(use_qwen: bool = False):
    config = get_config()
    stats = run_scan(config, use_qwen=use_qwen)
    return stats
