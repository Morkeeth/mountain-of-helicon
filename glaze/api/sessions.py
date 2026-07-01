from fastapi import APIRouter

from glaze.api.app import get_conn, get_config
from glaze.qwen import get_client
from glaze.sessions import generate_session_summary, get_session_summaries, get_review_drift

router = APIRouter()


@router.post("/sessions/summarize")
async def summarize_session():
    conn = get_conn()
    config = get_config()
    client = get_client(config)
    summary = generate_session_summary(conn, client, config)
    if not summary:
        return {"status": "no_session", "message": "Not enough recent reviews for a session summary (need 3+)"}
    return {"status": "ok", "summary": summary}


@router.get("/sessions")
async def list_sessions(limit: int = 10):
    conn = get_conn()
    return {"sessions": get_session_summaries(conn, limit)}


@router.get("/sessions/drift")
async def review_drift():
    conn = get_conn()
    return get_review_drift(conn)
