from fastapi import APIRouter

from glaze.api.app import get_conn
from glaze.eval import run_eval, get_eval_history

router = APIRouter()


@router.post("/eval/run")
async def eval_run():
    conn = get_conn()
    return run_eval(conn)


@router.get("/eval/history")
async def eval_history():
    conn = get_conn()
    return {"runs": get_eval_history(conn)}
