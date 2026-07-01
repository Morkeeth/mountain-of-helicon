from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from glaze.api.app import get_conn
from glaze.db import insert_review
from glaze.models import Review
from glaze.context_impact import link_review_to_context
from glaze.utility import update_reward

router = APIRouter()


class ReviewRequest(BaseModel):
    cube_id: str
    decision: str
    notes: str = ""
    time_to_review_seconds: float = 0.0


@router.post("/review")
async def submit_review(req: ReviewRequest):
    conn = get_conn()

    row = conn.execute("SELECT type, source, created_at FROM glaze_cubes WHERE id = ?", (req.cube_id,)).fetchone()
    if not row:
        return {"error": "cube not found"}

    now = datetime.utcnow()
    try:
        clean = row["created_at"].replace("Z", "")
        if "+" in clean:
            clean = clean.split("+")[0]
        created = datetime.fromisoformat(clean)
        age_days = (now - created).total_seconds() / 86400
    except (ValueError, AttributeError):
        age_days = 0

    review = Review(
        id=None,
        cube_id=req.cube_id,
        decision=req.decision,
        notes=req.notes,
        time_to_review_seconds=req.time_to_review_seconds,
        cube_age_days=round(age_days, 1),
        cube_type=row["type"],
        cube_source=row["source"],
        reviewed_at=now.isoformat(),
    )

    review_id = insert_review(conn, review)

    link_review_to_context(conn, req.cube_id, req.decision)

    reward_map = {"approved": 1.0, "revised": 0.8, "killed": 0.0}
    reward = reward_map.get(req.decision, 0.3)
    update_reward(conn, req.cube_id, reward)

    total_reviews = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    retrieval_stats = None
    if total_reviews > 0:
        acted = conn.execute("SELECT COUNT(*) FROM retrieval_log WHERE was_acted_on = 1").fetchone()[0]
        surfaced = conn.execute("SELECT COUNT(*) FROM retrieval_log WHERE was_surfaced = 1").fetchone()[0]
        retrieval_stats = {
            "precision": round(acted / surfaced, 3) if surfaced > 0 else 0,
            "total_surfaced": surfaced,
            "total_acted_on": acted,
        }

    return {"review_id": review_id, "cube_id": req.cube_id, "decision": req.decision,
            "retrieval_precision": retrieval_stats}


@router.get("/reviews")
async def list_reviews(cube_id: str | None = None, limit: int = 50):
    conn = get_conn()
    if cube_id:
        rows = conn.execute(
            "SELECT * FROM reviews WHERE cube_id = ? ORDER BY reviewed_at DESC LIMIT ?",
            (cube_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM reviews ORDER BY reviewed_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"reviews": [dict(r) for r in rows]}
