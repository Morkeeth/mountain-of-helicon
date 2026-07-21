"""API for governed Runs (V2.2) — Real Run Capture + Acceptance Closure.

Namespaced under /api/run/* (distinct from the existing RunCard /api/runs).

GET  /api/run/sessions   discover real safe local Claude Code sessions
POST /api/run/capture    capture one session into a RunRecord (imported)
POST /api/run/govern     wrap a capture in the governed lifecycle (objective+acceptance)
POST /api/run/accept     human verdict: accepted | rework | rollback (accepted promotes)
GET  /api/run/list       governed runs + captures for the Cockpit Runs view
GET  /api/run/detail     one run: capture facts + task_run + append-only events + receipt
"""
import json

from fastapi import APIRouter
from pydantic import BaseModel

from helicon.api.app import get_conn

router = APIRouter()


class CaptureReq(BaseModel):
    path: str


class GovernReq(BaseModel):
    capture_id: str
    objective: str
    acceptance: str


class AcceptReq(BaseModel):
    task_run_id: str
    verdict: str  # accepted | rework | rollback
    note: str = ""


@router.get("/run/sessions")
async def run_sessions(limit: int = 20):
    from helicon.capture import discover_sessions
    return {"sessions": discover_sessions(safe_only=True, limit=limit)}


@router.post("/run/capture")
async def run_capture(req: CaptureReq):
    from helicon.capture import capture_session
    return capture_session(get_conn(), req.path)


@router.post("/run/govern")
async def run_govern(req: GovernReq):
    from helicon.capture import govern_from_capture
    return govern_from_capture(get_conn(), req.capture_id, req.objective, req.acceptance)


@router.post("/run/accept")
async def run_accept(req: AcceptReq):
    from helicon import taskrun
    from helicon.capture import promote_prompt
    try:
        res = taskrun.accept_run(get_conn(), req.task_run_id, req.verdict, note=req.note)
    except taskrun.TaskRunError as e:
        return {"ok": False, "error": str(e)}
    # outcome gate: only an accepted run promotes its prompt
    if res.get("human_acceptance") == "accepted":
        res["promotion"] = promote_prompt(get_conn(), req.task_run_id)
    else:
        res["promotion"] = {"ok": False, "error": "not accepted — prompt not promoted"}
    return res


def _run_view(conn, cap) -> dict:
    """One Cockpit Run row: capture facts + governed state (if any)."""
    d = dict(cap)
    for k in ("session_ids", "tokens", "models", "artifact_manifest", "prompt_chain"):
        d[k] = json.loads(d.get(k) or ("[]" if k in ("session_ids", "artifact_manifest", "prompt_chain") else "{}"))
    tr = None
    if cap["task_run_id"]:
        tr = conn.execute("SELECT * FROM task_runs WHERE id=?", (cap["task_run_id"],)).fetchone()
    d["governed"] = dict(tr) if tr else None
    d["human_acceptance"] = tr["human_acceptance"] if tr else None
    d["status"] = tr["status"] if tr else "imported"
    d["needs_human"] = bool(tr and tr["human_acceptance"] == "pending")
    return d


@router.get("/run/list")
async def run_list():
    from helicon.capture import list_captures  # noqa: F401 (ensures module import)
    conn = get_conn()
    rows = conn.execute("SELECT * FROM run_captures ORDER BY captured_at DESC").fetchall()
    runs = [_run_view(conn, r) for r in rows]
    return {
        "runs": runs,
        "needs_you": sum(1 for r in runs if r["needs_human"]),
        "total": len(runs),
    }


@router.get("/run/detail")
async def run_detail(task_run_id: str = "", capture_id: str = ""):
    from helicon import taskrun
    conn = get_conn()
    if capture_id and not task_run_id:
        cap = conn.execute("SELECT task_run_id FROM run_captures WHERE id=?",
                           (capture_id,)).fetchone()
        task_run_id = cap["task_run_id"] if cap else ""
    cap = None
    if task_run_id:
        cap = conn.execute("SELECT * FROM run_captures WHERE task_run_id=?",
                           (task_run_id,)).fetchone()
    if cap is None and capture_id:
        cap = conn.execute("SELECT * FROM run_captures WHERE id=?", (capture_id,)).fetchone()
    if cap is None:
        return {"ok": False, "error": "run not found"}
    view = _run_view(conn, cap)
    events = []
    receipt = ""
    if task_run_id:
        events = [dict(e) for e in conn.execute(
            "SELECT ts, kind, actor, detail FROM run_events WHERE task_run_id=? ORDER BY id",
            (task_run_id,)).fetchall()]
        try:
            receipt = taskrun.render_receipt(conn, task_run_id)
        except Exception:
            receipt = ""
    view["events"] = events
    view["receipt"] = receipt
    return {"ok": True, "run": view}
