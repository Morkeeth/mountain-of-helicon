"""Read-only Workgraph API: connected work records, never fabricated scores."""
from fastapi import APIRouter, HTTPException
from helicon.wager import WagerError, list_work_cards, measure_workgraph, trace_work_card, workgraph_attention, workgraph_learning

router = APIRouter()


def _conn():
    """Resolve the app connection lazily to keep this router independently importable."""
    from helicon.api.app import get_conn
    return get_conn()


@router.get("/workgraph/cards")
async def work_cards(limit: int = 30):
    conn = _conn()
    return {
        "cards": list_work_cards(conn, limit=max(1, min(limit, 100))),
        "measurement": measure_workgraph(conn),
    }


@router.get("/workgraph/attention")
async def work_attention(limit: int = 30):
    return {"attention": workgraph_attention(_conn(), limit=max(1, min(limit, 100)))}

@router.get("/workgraph/learning")
async def work_learning():
    return workgraph_learning(_conn())


@router.get("/workgraph/cards/{wager_id}")
async def work_card_trace(wager_id: str):
    try:
        return trace_work_card(_conn(), wager_id)
    except WagerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
