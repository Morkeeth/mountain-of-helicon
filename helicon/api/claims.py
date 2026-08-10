"""Which of my agents' claims has anything independent checked?

Six incidents on 2026-08-10, each an instrument reporting healthy while broken:
a VPS probe said ok while the agents had no key · a skill benchmark said LIFTS
while its assertions were copied from the skills' own kill lists · a salvage said
done with no write path · an SSH tunnel said up with auth already dead · this
suite's own fleet said governed while the objectives had been reconstructed from
the sessions' first prompts · an orchestrator's SQL said 3 of 4 across a timezone.

Every one of them was a claim nobody had independently checked, rendered
identically to a claim that had been. So this route does one thing: it separates
what was CLAIMED from what was WRITTEN, what it COST, and whether anything other
than the claimant looked at it.

The ladder is derived from the store, not invented. As of today every run marked
`verified` carries `human_acceptance = 'pending'` and a receipt whose source is
`attached` — the agent's own evidence. Nothing in this store has been
independently checked, and the honest rendering of that is a level, not a badge.

Rule, learned from this suite's own bug: an empty store reports NO DATA, never
CLEAN. A level is never inferred from absence.
"""
import json

from fastapi import APIRouter

router = APIRouter()

# Ordered weakest-first. The UI must render these differently — that IS the product.
LEVELS = ["NO_DATA", "NO_CLAIM", "SELF_REPORTED", "HUMAN_RULED", "INDEPENDENTLY_CHECKED"]

LEVEL_MEANING = {
    "NO_DATA": "nothing was recorded — not a pass",
    "NO_CLAIM": "observed after the fact; no objective or acceptance test was ever declared",
    "SELF_REPORTED": "the agent that did the work is the only thing that says it worked",
    "HUMAN_RULED": "a human accepted or rolled it back",
    "INDEPENDENTLY_CHECKED": "evidence from a source that is not the agent that produced the work",
}


def _conn():
    from helicon.api.app import get_conn
    return get_conn()


def _receipt_source(raw) -> str | None:
    try:
        return (json.loads(raw or "{}") or {}).get("source")
    except (json.JSONDecodeError, TypeError):
        return None


def classify(row) -> tuple[str, str]:
    """One run -> (level, why). The `why` is shown, never summarised away."""
    outcome = row["verification_outcome"]
    human = row["human_acceptance"]
    source = _receipt_source(row["verification_receipt"])

    if row["task_class"] == "auto-observed":
        return "NO_CLAIM", "captured after the fact; no acceptance test was declared before the work"
    if human in ("accepted", "rework", "rollback"):
        return "HUMAN_RULED", f"a human ruled: {human}"
    if outcome == "verified" and source and source not in ("attached", "self", "agent"):
        return "INDEPENDENTLY_CHECKED", f"receipt source: {source}"
    if outcome == "verified":
        return "SELF_REPORTED", ("claims verified, but the receipt source is "
                                 f"{source or 'unrecorded'} and no human has ruled")
    if outcome == "contradicted":
        return "HUMAN_RULED", "contradicted — the claim failed a check"
    return "NO_DATA", "no verification outcome recorded"


@router.get("/claims")
async def claims(limit: int = 50):
    conn = _conn()
    limit = max(1, min(limit, 200))
    rows = conn.execute(
        """SELECT tr.id, tr.objective, tr.acceptance_test, tr.task_class, tr.repo_ref,
                  tr.verification_outcome, tr.verification_receipt, tr.human_acceptance,
                  tr.artifact_manifest, tr.opened_at, tr.run_id,
                  rc.cost, rc.output_tokens, rc.verified_ratio
           FROM task_runs tr
           LEFT JOIN run_cards rc ON rc.run_id = tr.run_id
           ORDER BY tr.opened_at DESC LIMIT ?""", (limit,)).fetchall()

    out, counts = [], {lvl: 0 for lvl in LEVELS}
    for r in rows:
        level, why = classify(r)
        counts[level] += 1
        try:
            written = len(json.loads(r["artifact_manifest"] or "[]"))
        except json.JSONDecodeError:
            written = 0
        out.append({
            "id": r["id"],
            "claimed": r["objective"],
            "acceptance": r["acceptance_test"],
            "written": written,                     # artifacts actually recorded
            "repo": (r["repo_ref"] or "").partition("@")[0].rstrip("/").split("/")[-1],
            # None, not 0: an unjoined run has UNKNOWN cost, and 0 would read as free.
            "cost": r["cost"], "output_tokens": r["output_tokens"],
            "cost_known": r["run_id"] is not None and r["cost"] is not None,
            "level": level, "why": why,
            "opened_at": r["opened_at"],
        })

    checked = counts["INDEPENDENTLY_CHECKED"] + counts["HUMAN_RULED"]
    return {
        "claims": out,
        "counts": counts,
        "levels": LEVELS,
        "meaning": LEVEL_MEANING,
        "total": len(out),
        "independently_checked": checked,
        # The headline, and it is deliberately not a percentage when there is
        # nothing to divide: an empty store reports NO DATA, never CLEAN.
        "headline": (f"{checked} of {len(out)} claims have been checked by something "
                     f"other than the agent that made them") if out
                    else "NO DATA — nothing recorded, which is not a pass",
    }
