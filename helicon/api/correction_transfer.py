"""Loopback-only API for the reviewed correction-transfer teaching card."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from helicon.api.context_review import local_request
from helicon.config import helicon_home
from helicon.correction_transfer import (
    AUTHORED_EXAMPLE,
    CorrectionTransferStore,
    TransferError,
)


router = APIRouter(dependencies=[Depends(local_request)])


def store() -> CorrectionTransferStore:
    return CorrectionTransferStore(Path(helicon_home()) / "correction-transfer")


def failed(exc: Exception):
    raise HTTPException(409, str(exc)) from exc


class ProposalIn(BaseModel):
    original_draft: str = Field(min_length=1, max_length=100_000)
    edited_draft: str = Field(min_length=1, max_length=100_000)
    proposed_rule: str = Field(min_length=1, max_length=4_000)
    scope: dict[str, str]
    operation: dict[str, str]
    explicit_instruction: str = Field(default="", max_length=4_000)
    inferred_reason: str = Field(default="", max_length=4_000)
    supersedes: str | None = None
    example_label: str = Field(default="", max_length=500)


class DecisionIn(BaseModel):
    decision: str


class ScopeIn(BaseModel):
    scope: dict[str, str]


class CompareIn(BaseModel):
    cases: list[dict] = Field(min_length=1, max_length=20)


@router.get("/correction-transfer/example")
def example():
    """Authored fixture only. Reading it creates no correction or decision."""
    return AUTHORED_EXAMPLE


@router.post("/correction-transfer/proposals")
def propose(body: ProposalIn):
    try:
        return store().propose(actor="local-reviewer", **body.model_dump())
    except (TransferError, OSError) as exc:
        failed(exc)


@router.post("/correction-transfer/{rule_id}/decision")
def decide(rule_id: str, body: DecisionIn):
    try:
        return store().decide(rule_id, body.decision, "local-reviewer")
    except (TransferError, OSError) as exc:
        failed(exc)


@router.post("/correction-transfer/{rule_id}/scope")
def change_scope(rule_id: str, body: ScopeIn):
    try:
        return store().change_scope(rule_id, body.scope, "local-reviewer")
    except (TransferError, OSError) as exc:
        failed(exc)


@router.post("/correction-transfer/{rule_id}/undo")
def undo(rule_id: str):
    try:
        return store().undo(rule_id, "local-reviewer")
    except (TransferError, OSError) as exc:
        failed(exc)


@router.get("/correction-transfer/{rule_id}")
def inspect(rule_id: str):
    try:
        return store().get(rule_id)
    except (TransferError, OSError) as exc:
        failed(exc)


@router.post("/correction-transfer/compare")
def compare(body: CompareIn):
    try:
        return store().compare(body.cases)
    except (TransferError, OSError) as exc:
        failed(exc)
