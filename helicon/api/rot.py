"""The rot exam and the judge bench, as surfaces.

Two endpoints, two very different cost profiles, and the difference is the whole
design:

  GET /api/rot    — the 12-class exam. Zero LLM calls by design, so it runs live
                    on every request and the number on screen is the number now.
  GET /api/judge  — the LAST SAVED judge bench. Never runs one: a bench is live
                    cross-provider inference (real money, real minutes), so a page
                    load must not trigger it. No saved run renders as "no saved
                    run" plus the command that makes one. Nothing is synthesised.
"""
import os

from fastapi import APIRouter

from helicon.api.app import get_conn

router = APIRouter()


@router.get("/rot")
async def rot_exam():
    """Run the 12-class rot exam live against the real store.

    repo_root is passed so R2 (doc-drift) checks the docs of THIS checkout rather
    than silently reporting `unmeasured`.
    """
    from helicon.rot import run_rot_exam

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return run_rot_exam(get_conn(), repo_root=repo_root)


@router.get("/judge")
async def judge_bench():
    """The last saved judge bench, or an honest empty state.

    `ran: false` is a real answer, not an error. The UI renders the command
    instead of a chart, because a fabricated benchmark number in a hackathon
    submission is fraud, not a placeholder.
    """
    from helicon.judge_bench import latest_judge_run

    run = latest_judge_run(get_conn())
    if not run:
        return {
            "ran": False,
            "command": "helicon judge-bench --set all --save",
            "why": ("A bench is live cross-provider inference, so it is never run "
                    "from the dashboard. Run the command to produce one."),
        }
    return {"ran": True, **run}
