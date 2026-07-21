"""API surface for the V2 Cockpit — the opening agent-output review queue.

`GET /api/cockpit`           the ORIENT view: every safe terminal + claims + verdicts
`GET /api/cockpit/artifact`  INSPECT: one artifact's content in native review form

Read-only. Reuses the wired review_terminals verify() engine via helicon.cockpit.
The heavy per-request work is a capped git scan of a SAFE allowlist of repos.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from helicon.api.app import get_conn, get_config

router = APIRouter()


class RuleReq(BaseModel):
    terminal: str
    repo_path: str
    claim: dict
    decision: str  # keep | revise | reject
    correction: str = ""


class UndoReq(BaseModel):
    finding_id: int


@router.get("/cockpit")
async def cockpit(run: bool = False):
    """ORIENT + COMPARE: the finite review queue. `run=true` actually re-runs
    claimed test suites (slow, honest); default is a fast git-grounded read."""
    from helicon.cockpit import cockpit_view
    return cockpit_view(get_conn(), get_config(), run=run)


@router.get("/cockpit/artifact")
async def cockpit_artifact(repo_path: str, kind: str, ref: str):
    """INSPECT: render one artifact natively (markdown / diff). Privacy is
    re-checked on every load; a private path is never served."""
    from helicon.cockpit import load_artifact, SAFE_TERMINALS, _is_private
    import os
    # the repo must be one of the safe terminals' repos, never an arbitrary path
    base = os.path.basename(repo_path.rstrip("/")).lower()
    safe = base in {s.lower() for s in SAFE_TERMINALS} or base.startswith("helicon")
    if not safe or _is_private(repo_path):
        return {"type": "blocked", "text": "", "why": "repo not in safe allowlist"}
    return load_artifact(repo_path, kind, ref)


@router.post("/cockpit/rule")
async def cockpit_rule(req: RuleReq):
    """RULE + APPLY one claim (keep/revise/reject). Revise captures the
    correction verbatim; returns a receipt + continuity proof + undo target."""
    from helicon.cockpit import rule_claim
    return rule_claim(get_conn(), get_config(), req.terminal, req.repo_path,
                      req.claim, req.decision, req.correction)


@router.post("/cockpit/undo")
async def cockpit_undo(req: UndoReq):
    """UNDO a ruling — delete the correction cube and re-open the finding."""
    from helicon.cockpit import unrule_claim
    return unrule_claim(get_conn(), req.finding_id)
