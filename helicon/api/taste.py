"""Taste bridge API — the HTTP wire Taste Machine calls.

TM POSTs a verdict the moment the human rules (right after its `labels` insert),
and GETs the guard before showing a draft in REVIEW, so an already-ruled shape is
suppressed instead of wasting a ruling.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from helicon.api.app import get_conn
from helicon.taste import ingest_verdict, taste_guard

router = APIRouter()


class VerdictIn(BaseModel):
    artifact_hash: str = ""
    artifact_id: str = ""
    kind: str = ""
    content: str = ""
    move: str = ""
    reason: str = ""
    human_verdict: str = ""
    machine_verdict: str = ""
    scores: dict = {}
    decided_at: str = ""


@router.post("/taste/verdict")
async def taste_verdict(v: VerdictIn):
    """Remember a Taste Machine ruling."""
    return ingest_verdict(get_conn(), v.model_dump())


@router.get("/taste/guard")
async def taste_guard_ep(hash: str = "", kind: str = "", move: str = ""):
    """Have we already ruled this output (exact) or this shape (kind, move)?"""
    return taste_guard(get_conn(), artifact_hash=hash or None,
                       kind=kind or None, move=move or None)
