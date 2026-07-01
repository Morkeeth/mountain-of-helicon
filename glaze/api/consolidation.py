from fastapi import APIRouter

from glaze.api.app import get_conn, get_config
from glaze.consolidation import find_clusters, run_consolidation, get_consolidations
from glaze.qwen import get_client as _get_client

router = APIRouter()


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
async def trigger_consolidation(use_qwen: bool = True, max_clusters: int = 10):
    conn = get_conn()
    qwen_client = _get_client(get_config()) if use_qwen else None
    result = run_consolidation(conn, qwen_client, max_clusters)
    return result


@router.get("/consolidations/tiers")
async def get_tiers():
    conn = get_conn()
    now_sql = "julianday('now')"
    hot = conn.execute(
        f"SELECT COUNT(*) FROM glaze_cubes WHERE review_status != 'killed' AND ({now_sql} - julianday(created_at)) <= 7"
    ).fetchone()[0]
    warm = conn.execute(
        f"SELECT COUNT(*) FROM glaze_cubes WHERE review_status != 'killed' AND ({now_sql} - julianday(created_at)) > 7 AND ({now_sql} - julianday(created_at)) <= 30"
    ).fetchone()[0]
    cold = conn.execute(
        f"SELECT COUNT(*) FROM glaze_cubes WHERE review_status != 'killed' AND ({now_sql} - julianday(created_at)) > 30"
    ).fetchone()[0]
    consolidations = conn.execute("SELECT COUNT(*) FROM consolidations").fetchone()[0]
    total_merged = conn.execute("SELECT COALESCE(SUM(cube_count), 0) FROM consolidations").fetchone()[0]
    return {
        "hot": hot, "warm": warm, "cold": cold,
        "consolidations": consolidations, "total_merged": total_merged,
    }
