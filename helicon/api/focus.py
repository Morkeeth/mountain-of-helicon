"""Focus API — memory state -> next moves, and routing a move out of Helicon
to where work actually happens (the agent, or the vault). The loop closes here:
a move leaves as a paste-ready agent prompt and/or a markdown note in the vault.
"""
import os
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from helicon.api.app import get_conn, get_config
from helicon.focus import generate_next_moves

router = APIRouter()


@router.get("/focus/moves")
async def focus_moves():
    """Generate cited next-moves from the current memory state (Qwen)."""
    return generate_next_moves(get_conn(), get_config())


def _vault_dir(config: dict) -> str | None:
    """Configured Obsidian vault, if any. Kept config-driven so the OSS tool
    never hardcodes a personal path; falls back to a local file when unset."""
    conns = (config or {}).get("connectors", {}) or {}
    obs = conns.get("obsidian", {}) or {}
    path = obs.get("path") or obs.get("vault") or (config or {}).get("obsidian_path")
    if path:
        path = os.path.expanduser(path)
        if os.path.isdir(path):
            return path
    return None


def _agent_prompt(move: dict) -> str:
    receipts = move.get("receipts", [])
    cites = "\n".join(f"- [{r.get('ref')}] {r.get('why','')[:160]}" for r in receipts)
    return (f"# Next move: {move.get('title','')}\n\n"
            f"{move.get('body','')}\n\n"
            f"_Why (from your memory audit):_ {move.get('rationale','')}\n"
            f"_Grounded in:_\n{cites}\n")


class RouteBody(BaseModel):
    move: dict
    destination: str = "prompt"  # "prompt" (agent) | "vault"


@router.post("/focus/route")
async def focus_route(body: RouteBody):
    """Route a move out of Helicon. destination=prompt returns paste-ready agent
    text; destination=vault writes a markdown note to the configured vault (or a
    local data/ file) so the review becomes forward motion, not a cleaned DB."""
    move = body.move or {}
    prompt = _agent_prompt(move)

    if body.destination == "vault":
        config = get_config()
        vault = _vault_dir(config)
        stamp = datetime.utcnow().strftime("%Y-%m-%d")
        if vault:
            target_dir = os.path.join(vault, "00 Dashboard")
            os.makedirs(target_dir, exist_ok=True)
            target = os.path.join(target_dir, "helicon-next-moves.md")
        else:
            target_dir = os.path.join(os.getcwd(), "data", "next-moves")
            os.makedirs(target_dir, exist_ok=True)
            target = os.path.join(target_dir, f"next-moves-{stamp}.md")
        header = "" if os.path.exists(target) else "# Helicon — next moves\n\n"
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(f"{header}## {stamp} — {move.get('title','')}\n\n{prompt}\n---\n\n")
        return {"routed": "vault", "path": target, "prompt": prompt}

    return {"routed": "prompt", "prompt": prompt}
