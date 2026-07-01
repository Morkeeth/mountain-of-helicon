from fastapi import APIRouter

from glaze.api.app import get_conn, get_config

router = APIRouter()


@router.get("/connectors")
async def list_connectors():
    config = get_config()
    conn = get_conn()

    connectors_config = config.get("connectors", {})
    result = []

    for name, cfg in connectors_config.items():
        enabled = cfg.get("enabled", True)
        count = conn.execute(
            "SELECT COUNT(*) FROM glaze_cubes WHERE source = ?", (name,)
        ).fetchone()[0]
        result.append({
            "name": name,
            "enabled": enabled,
            "cube_count": count,
        })

    return {"connectors": result}
