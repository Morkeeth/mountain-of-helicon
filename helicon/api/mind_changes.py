"""WHAT CHANGED MY MIND? over local memory content. Loopback only.

The response carries `served_by` so the dashboard, the menu bar app and a
terminal call can each show which build and source produced the same answer.
Personal paths and quotes stay on this machine; the route is never proxied.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from helicon.api.context_review import local_request
from helicon.mind_changes import answer, default_sources, save_lesson, served_by

router = APIRouter(dependencies=[Depends(local_request)])

LESSON_DIR = Path.home() / ".helicon" / "lessons"


@router.get("/mind-changes")
async def mind_changes(q: str = "", window: int = 7, as_of: str | None = None):
    try:
        result = answer(q, window=window, as_of=as_of, **default_sources())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    result["served_by"] = served_by()
    return result


@router.get("/mind-changes/identity")
async def identity():
    return {"served_by": served_by(), "sources": default_sources()}


class LessonIn(BaseModel):
    lesson: str
    prompt: str
    sources: list[dict]


@router.post("/mind-changes/lesson")
async def lesson(body: LessonIn):
    """Save one edited lesson as a local packet file a receiving assistant reads."""
    try:
        saved = save_lesson(body.lesson, body.prompt, body.sources, LESSON_DIR)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"path": saved["path"], "sha256": saved["sha256"], "served_by": served_by(),
            "delivered": False,
            "note": "Saved locally. Saving is not delivery; a receiving assistant must read this file."}
