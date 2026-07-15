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
import time
from datetime import datetime, timezone

from fastapi import APIRouter

from helicon.api.app import get_conn

router = APIRouter()

# The exam is LLM-free but not free: R8 replays real retrieval for every
# captured snapshot, which measured ~16s of a ~21s run on the demo store. That
# is fine for a nightly `watch` tick and much too slow for a tab, so the result
# is held briefly and stamped with when it ran. The cache is never silent: the
# response always carries ran_at + cached, the surface always prints the time,
# and ?fresh=1 forces a real re-run. A cached verdict that presents itself as
# live would be exactly the rot this project exists to catch.
_ROT_TTL_S = 180
_cache: dict = {"res": None, "mono": 0.0, "ran_at": None, "took_s": None}


@router.get("/rot")
async def rot_exam(fresh: int = 0):
    """The 12-class rot exam against the real store.

    repo_root is passed so R2 (doc-drift) checks the docs of THIS checkout
    rather than silently reporting `unmeasured`.
    """
    from helicon.rot import run_rot_exam

    if not fresh and _cache["res"] is not None and \
            (time.monotonic() - _cache["mono"]) < _ROT_TTL_S:
        return {**_cache["res"], "ran_at": _cache["ran_at"],
                "took_s": _cache["took_s"], "cached": True}

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    t0 = time.monotonic()
    res = run_rot_exam(get_conn(), repo_root=repo_root)
    took = round(time.monotonic() - t0, 1)
    _cache.update({"res": res, "mono": time.monotonic(), "took_s": took,
                   "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return {**res, "ran_at": _cache["ran_at"], "took_s": took, "cached": False}


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
