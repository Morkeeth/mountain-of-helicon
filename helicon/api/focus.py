"""Focus API — memory state -> next moves, and routing a move out of Helicon
to where work actually happens (the agent, or the vault). The loop closes here:
a move leaves as a paste-ready agent prompt and/or a markdown note in the vault.
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from helicon.api.app import get_conn, get_config
from helicon.focus import generate_next_moves

router = APIRouter()


@router.get("/focus/moves")
async def focus_moves():
    """Generate cited next-moves from the current memory state (Qwen)."""
    return generate_next_moves(get_conn(), get_config())


@router.get("/stores/audit")
async def stores_audit():
    """Audit a configured external memory store (Mem0 — the backend Alibaba's own
    docs recommend) read-only, and run the rot exam on what it stored. Config:
    a `mem0_audit` block with {api_key, user_id, rename:[old,new]}."""
    import os
    import tempfile
    from helicon.db import init_db
    from helicon.scanner import run_scan
    from helicon.rot import run_rot_exam
    from helicon.aliases import add_alias

    cfg = get_config()
    m = cfg.get("mem0_audit") or {}
    if not m.get("api_key"):
        return {"configured": False}
    db = os.path.join(tempfile.gettempdir(), "helicon-store-audit.db")
    if os.path.exists(db):
        os.remove(db)
    conn = init_db(db)
    scfg = {"db_path": db, "embeddings": cfg.get("embeddings", {}),
            "qwen_api_key": cfg.get("qwen_api_key", ""), "qwen_base_url": cfg.get("qwen_base_url", ""),
            "connectors": {"mem0": {"api_key": m["api_key"], "user_id": m.get("user_id", "default"), "limit": 500}}}
    stats = run_scan(scfg)
    if m.get("rename") and len(m["rename"]) == 2:
        add_alias(conn, m["rename"][0], m["rename"][1], "2026-01-01T00:00:00", note="rename the store recorded")
    res = run_rot_exam(conn)
    rotten = [c for c in res["checks"] if c["verdict"] == "ROT FOUND"]
    return {
        "configured": True, "store": "Mem0",
        "memories": stats.get("total_in_db", 0),
        "rot_found": res["rot_found"], "classes": res["classes"],
        "findings": [{"id": c["id"], "name": c["name"], "receipt": c["receipt"]} for c in rotten],
    }


@router.get("/setup-report")
async def setup_report():
    """The graded MemoryAgent report card — how healthy your agent's memory
    setup is, scored live against the Track-1 criteria. Heavy (runs the battery
    + cross-source pairing), so it's an explicit action, not an auto-load."""
    from helicon.report import memoryagent_report
    from helicon.qwen import get_client
    cfg = get_config()
    return memoryagent_report(get_conn(), client=get_client(cfg))


def _vault_dir(config: dict) -> str | None:
    """Configured Obsidian vault, if any. Kept config-driven so the OSS tool
    never hardcodes a personal path; falls back to a local file when unset."""
    conns = (config or {}).get("connectors", {}) or {}
    obs = conns.get("obsidian", {}) or {}
    path = obs.get("vault_path") or obs.get("path") or obs.get("vault") or (config or {}).get("obsidian_path")
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
        stamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d")
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


@router.get("/portrait")
async def portrait():
    """The reading: a grounded portrait of who the record shows you are, plus
    the process arc. Qwen narrates a deterministic digest (heavy-ish, so it is
    an explicit tab load, not an auto-poll)."""
    from helicon.portrait import build_portrait
    from helicon.qwen import get_client
    cfg = get_config()
    return build_portrait(get_conn(), cfg, client=get_client(cfg))


@router.get("/consistency")
async def consistency():
    """The consistency gate: does the operator's memory index still match its
    directory? Deterministic. Defaults to the Claude Code auto-memory MEMORY.md
    or a configured index."""
    from helicon.consistency import audit_index, default_index
    cfg = get_config()
    idx = default_index(cfg)
    if not idx:
        return {"ok": False, "reason": "no index configured or found"}
    return audit_index(idx)


@router.get("/volatility/scan")
async def volatility_scan():
    """The volatility gate: which stored memories are fast facts that belong in
    the live layer, not memory. Deterministic suspects, then Qwen sentences the
    top ones with a tier + the event that would make each wrong."""
    from helicon.qwen import get_client
    from helicon.volatility import scan_volatility
    cfg = get_config()
    return scan_volatility(get_conn(), cfg, client=get_client(cfg))


class VolatilityAct(BaseModel):
    action: str                       # "move" | "stamp"
    source_ref: str
    title: str = ""
    excerpt: str = ""
    stale_when: str = ""


@router.post("/volatility/act")
async def volatility_act(body: VolatilityAct):
    """One-click fix. move: copy the fast fact to the live layer and banner the
    source. stamp: add as_of + stale_when to a slow fact's frontmatter."""
    from helicon.volatility import move_to_live_layer, stamp_decay
    cfg = get_config()
    if body.action == "stamp":
        return stamp_decay(body.source_ref, cfg, body.stale_when)
    if body.action == "move":
        return move_to_live_layer(body.source_ref, body.title, body.excerpt, cfg)
    return {"ok": False, "reason": f"unknown action {body.action!r}"}
