"""The doorway API — the board every agent walks through.

`GET /api/doorway/board`  every repo under the code root + its live loaded-token
                          cost (CLAUDE.md, @imports, other agent-rules files).

Read-only, filesystem-backed. The root defaults to ~/CODE and is overridable by
query param or the `code_root` config key.
"""
from fastapi import APIRouter

from helicon.api.app import get_config
from helicon.doorway import list_repos

router = APIRouter()


@router.get("/doorway/board")
async def doorway_board(root: str = ""):
    """The board: repos + per-repo loaded-token cost, heaviest first."""
    return list_repos(root=root or None, config=get_config())
