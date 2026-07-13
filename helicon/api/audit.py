from datetime import datetime, timezone

from fastapi import APIRouter
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


@router.post("/audit/resolve-identity")
async def resolve_identity_finding(req: ResolveIdentityRequest):
    from helicon.identity import resolve_identity
    conn = get_conn()
    return resolve_identity(conn, req.finding_id, req.canonical)


@router.post("/audit/confirm")
async def confirm_finding(req: ConfirmRequest):
    conn = get_conn()
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
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
    return {"finding_id": req.finding_id, "decision": req.decision, "killed_cubes": killed_cubes}
