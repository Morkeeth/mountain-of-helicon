from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from helicon.api.app import get_conn, get_config
from helicon.audit import run_audit
from helicon.db import get_audit_results
from helicon.qwen import get_client as _get_client

router = APIRouter()


@router.get("/audit")
async def list_audit(pending_only: bool = True):
    conn = get_conn()
    return {"findings": get_audit_results(conn, pending_only)}


@router.post("/audit/run")
async def trigger_audit():
    conn = get_conn()
    config = get_config()
    client = _get_client(get_config())
    results = run_audit(conn, config, client)
    return results


class ConfirmRequest(BaseModel):
    finding_id: int
    decision: str
    notes: str = ""


class ResolveIdentityRequest(BaseModel):
    finding_id: int
    canonical: str


class ResolveRelationRequest(BaseModel):
    finding_id: int
    verdict: str = "phantom"


@router.post("/audit/resolve-relation")
async def resolve_relation_finding(req: ResolveRelationRequest):
    from helicon.relations import resolve_relation
    conn = get_conn()
    return resolve_relation(conn, req.finding_id, req.verdict)


@router.post("/audit/resolve-identity")
async def resolve_identity_finding(req: ResolveIdentityRequest):
    from helicon.identity import resolve_identity
    conn = get_conn()
    return resolve_identity(conn, req.finding_id, req.canonical)


@router.post("/audit/confirm")
async def confirm_finding(req: ConfirmRequest):
    conn = get_conn()
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # A dismissal only becomes law if it carries a REASON: gold.py emits a
    # precedent for `hd == "dismissed" and d.get("dismiss_reason")` and nothing
    # otherwise. This endpoint accepted `notes` and dropped them on the floor,
    # never touching details, so a dismissal ruled from the DASHBOARD — the
    # surface a judge actually uses, and the only one a future HTTP client has —
    # silently failed to become a precedent, while the identical ruling from the
    # CLI compiled fine. The thesis is "a human rules once and the agent obeys
    # next time"; over HTTP it was "a human rules once and nothing happens".
    # Route through the same function the CLI uses so there is one path, with
    # its already-decided guard, rather than two that disagree.
    precedent = False
    if req.decision == "dismissed" and req.notes.strip():
        from helicon.pairing import dismiss_finding
        res = dismiss_finding(conn, req.finding_id, req.notes.strip())
        if not res.get("ok"):
            raise HTTPException(status_code=400, detail=res.get("error"))
        return {"finding_id": req.finding_id, "decision": req.decision,
                "killed_cubes": [], "precedent": True}

    conn.execute(
        "UPDATE audit_log SET human_decision = ?, resolved_at = ? WHERE id = ?",
        (req.decision, now, req.finding_id),
    )

    killed_cubes = []
    if req.decision == "acted":
        row = conn.execute(
            "SELECT target_id, audit_type FROM audit_log WHERE id = ?",
            (req.finding_id,),
        ).fetchone()
        if row:
            cube_id = row["target_id"]
            audit_type = row["audit_type"]
            if audit_type in ("temporal", "decay"):
                conn.execute(
                    "UPDATE helicon_cubes SET review_status = 'killed' WHERE id = ?",
                    (cube_id,),
                )
                killed_cubes.append(cube_id)
                conn.execute(
                    "INSERT OR IGNORE INTO reviews (cube_id, decision, notes, reviewed_at, time_to_review_seconds) "
                    "VALUES (?, 'killed', ?, ?, 0)",
                    (cube_id, f"Killed via audit: {audit_type}", now),
                )

    conn.commit()
    # precedent False: a dismissal with no reason still clears the queue and
    # still dedups, but it compiles to no law. Say so rather than imply it.
    return {"finding_id": req.finding_id, "decision": req.decision,
            "killed_cubes": killed_cubes, "precedent": False}
