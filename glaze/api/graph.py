from fastapi import APIRouter

from glaze.api.app import get_conn, get_config
from glaze.graph import build_graph, get_graph_data, get_entity_details
from glaze.qwen import get_client

router = APIRouter()


@router.get("/graph")
async def graph_data():
    conn = get_conn()
    data = get_graph_data(conn)
    return data


@router.post("/graph/build")
async def build_graph_endpoint(use_qwen: bool = False):
    conn = get_conn()
    config = get_config()
    qwen_client = get_client(config) if use_qwen else None
    stats = build_graph(conn, qwen_client)
    return stats


@router.get("/graph/entity/{entity_id}")
async def entity_detail(entity_id: str):
    conn = get_conn()
    result = get_entity_details(conn, entity_id)
    if not result:
        return {"error": "not found"}
    return result
