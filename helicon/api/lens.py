"""Memory Causal Lens API — the memories behind an answer."""
from fastapi import APIRouter

from helicon.api.app import get_conn
from helicon.provenance import memory_provenance

router = APIRouter()


@router.get("/lens")
async def lens(task: str = "", k: int = 8):
    """Trace the memories the agent retrieved to produce an answer."""
    if not task.strip():
        return {"task": task, "memories": []}
    conn = get_conn()
    return {"task": task, "memories": memory_provenance(conn, task, k=k)}
