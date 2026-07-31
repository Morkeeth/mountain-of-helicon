"""The doorway API — the board every agent walks through.

`GET  /api/doorway/board`   every repo under the code root + live loaded-token cost
`GET  /api/doorway/repo`    one repo's loaded lines, each with a probe verdict
`POST /api/doorway/cold`    demote a line (or whole doc) to cold: kept, loads nothing
`POST /api/doorway/warm`    bring a cold line back into the loaded set

Read-only except the two explicit cold mutations. Root defaults to ~/CODE and is
overridable by query param or the `code_root` config key.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from helicon.api.app import get_conn, get_config
from helicon import doorway

router = APIRouter()


class ColdReq(BaseModel):
    repo: str
    ref: str
    tokens: int = 0
    reason: str = ""


class WarmReq(BaseModel):
    repo: str
    ref: str


@router.get("/doorway/board")
async def doorway_board(root: str = ""):
    """The board: repos + per-repo loaded-token cost, heaviest first. Cold lines
    are subtracted, so the total falls as lines are demoted."""
    return doorway.list_repos(root=root or None, config=get_config(), conn=get_conn())


@router.get("/doorway/repo")
async def doorway_repo(repo: str, root: str = ""):
    """One repo's loaded lines, each carrying a probe verdict + its cold state."""
    root_dir = doorway.resolve_root(root or None, get_config())
    import os
    repo_path = repo if os.path.isabs(repo) else os.path.join(root_dir, repo)
    return doorway.repo_detail(get_conn(), repo_path, get_config())


@router.post("/doorway/cold")
async def doorway_cold(req: ColdReq):
    """Demote a line/doc to cold. The counter on the board falls by `tokens`."""
    return doorway.demote(get_conn(), req.repo, req.ref, req.tokens, req.reason)


@router.post("/doorway/warm")
async def doorway_warm(req: WarmReq):
    """Undo a demotion — the line loads again."""
    return doorway.promote(get_conn(), req.repo, req.ref)
