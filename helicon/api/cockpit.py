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
    pair_key: str  # the claim is re-derived server-side by (terminal, pair_key)
    decision: str  # keep | revise | reject
    correction: str = ""


class UndoReq(BaseModel):
    finding_id: int


class PropagateReq(BaseModel):
    correction_cube: str = ""


@router.get("/cockpit")
async def cockpit(run: bool = False):
    """ORIENT + COMPARE: the finite review queue. `run=true` actually re-runs
    claimed test suites (slow, honest); default is a fast git-grounded read."""
    from helicon.cockpit import cockpit_view
    return cockpit_view(get_conn(), get_config(), run=run)


@router.get("/cockpit/artifact")
async def cockpit_artifact(repo_path: str, kind: str, ref: str,
                           expected_hash: str = ""):
    """INSPECT: render one artifact natively (markdown / diff). All allowlist +
    containment + privacy enforcement is server-side in load_artifact (P0-1) —
    the caller-supplied path is validated, never trusted."""
    from helicon.cockpit import load_artifact
    return load_artifact(repo_path, kind, ref, expected_hash=expected_hash)


@router.post("/cockpit/rule")
async def cockpit_rule(req: RuleReq):
    """RULE + APPLY one claim (keep/revise/reject), addressed by
    (terminal, pair_key). The claim + verdict are re-derived server-side; the
    browser payload is never trusted to assert them (P0-2)."""
    from helicon.cockpit import rule_claim
    return rule_claim(get_conn(), get_config(), req.terminal, req.pair_key,
                      req.decision, req.correction)


@router.post("/cockpit/undo")
async def cockpit_undo(req: UndoReq):
    """UNDO a ruling — delete the correction cube and re-open the finding."""
    from helicon.cockpit import unrule_claim
    return unrule_claim(get_conn(), req.finding_id)


@router.post("/cockpit/propagate")
async def cockpit_propagate(req: PropagateReq):
    """PROVE CONTINUITY: compile corrections into the next agent's context
    files (sandboxed) and prove the correction is included. Real ~/.claude is
    a human gate."""
    from helicon.cockpit import propagate_correction
    return propagate_correction(get_conn(), get_config(), req.correction_cube or None)
