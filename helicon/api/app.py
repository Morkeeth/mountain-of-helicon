import asyncio
import hmac
import json
import os
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles

from helicon.config import load_config
from helicon.db import init_db
from helicon.qwen import set_cache_db
from helicon.triage import init_triage_table

_conn: sqlite3.Connection | None = None
_config: dict = {}
_MAX_MCP_REQUEST_BYTES = 1024 * 1024


def _resolve_web_dir(repo_root: str) -> str | None:
    """The dashboard's built assets: prefer static/ (populated by the Cloud
    Shell / deploy copy), then web/dist (the local `npm run build` output).
    None if neither has an index.html — in which case serve says what to run.

    web/dist used to be COMMITTED, "so a fresh clone renders without a build
    step". It did not render a fresh clone's UI; it rendered a fossil. The
    tracked bundle's last commit was 2026-07-23 01:38 while web/src had moved
    on to 2026-07-26 23:38, so a fresh clone — the cloud-VM case the repo's own
    AGENTS.md sets up — served a three-day-old dashboard while the code claimed
    it was current. A stale UI that renders is worse than an absent one that
    explains itself, because nothing about it looks wrong.
    """
    for cand in ("static", os.path.join("web", "dist")):
        d = os.path.join(repo_root, cand)
        if os.path.isfile(os.path.join(d, "index.html")) and \
           os.path.isdir(os.path.join(d, "assets")):
            return d
    return None


def get_conn() -> sqlite3.Connection:
    return _conn


def get_config() -> dict:
    return _config


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _conn, _config
    _config = load_config()
    db_path = _config.get("db_path", "data/helicon.db")
    _conn = init_db(db_path)
    set_cache_db(_conn)
    init_triage_table(_conn)
    yield
    if _conn:
        _conn.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Mountain of Helicon", version="0.1.0", lifespan=lifespan)
    mcp_lock = asyncio.Lock()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    password = os.environ.get("HELICON_PASSWORD")
    mcp_token = os.environ.get("HELICON_MCP_TOKEN")
    if password:
        @app.middleware("http")
        async def auth_middleware(request: Request, call_next):
            if request.url.path.startswith("/api/"):
                token = request.headers.get("Authorization", "").replace("Bearer ", "")
                if token != password:
                    return JSONResponse(status_code=401, content={"error": "unauthorized"})
            return await call_next(request)

    from helicon.api.cubes import router as cubes_router
    from helicon.api.review import router as review_router
    from helicon.api.score import router as score_router
    from helicon.api.patterns import router as patterns_router
    from helicon.api.audit import router as audit_router
    from helicon.api.lens import router as lens_router
    from helicon.api.taste import router as taste_router
    from helicon.api.connectors import router as connectors_router
    from helicon.api.graph import router as graph_router
    from helicon.api.search import router as search_router
    from helicon.api.sessions import router as sessions_router
    from helicon.api.triage import router as triage_router
    from helicon.api.projects import router as projects_router
    from helicon.api.eval import router as eval_router
    from helicon.api.playbooks import router as playbooks_router
    from helicon.api.consolidation import router as consolidation_router
    from helicon.api.tokens import router as tokens_router
    from helicon.api.integrity import router as integrity_router
    from helicon.api.findings import router as findings_router
    from helicon.api.govern import router as govern_router
    from helicon.api.log import router as log_router
    from helicon.api.focus import router as focus_router
    from helicon.api.intelligence import router as intelligence_router
    from helicon.api.rot import router as rot_router
    from helicon.api.brief import router as brief_router
    from helicon.api.cockpit import router as cockpit_router
    from helicon.api.runs2 import router as runs2_router
    from helicon.api.doorway import router as doorway_router

    app.include_router(cubes_router, prefix="/api")
    app.include_router(review_router, prefix="/api")
    app.include_router(score_router, prefix="/api")
    app.include_router(patterns_router, prefix="/api")
    app.include_router(audit_router, prefix="/api")
    app.include_router(lens_router, prefix="/api")
    app.include_router(taste_router, prefix="/api")
    app.include_router(connectors_router, prefix="/api")
    app.include_router(graph_router, prefix="/api")
    app.include_router(search_router, prefix="/api")
    app.include_router(sessions_router, prefix="/api")
    app.include_router(triage_router, prefix="/api")
    app.include_router(projects_router, prefix="/api")
    app.include_router(eval_router, prefix="/api")
    app.include_router(playbooks_router, prefix="/api")
    app.include_router(consolidation_router, prefix="/api")
    app.include_router(tokens_router, prefix="/api")
    app.include_router(integrity_router, prefix="/api")
    app.include_router(findings_router, prefix="/api")
    app.include_router(govern_router, prefix="/api")
    app.include_router(log_router, prefix="/api")
    app.include_router(focus_router, prefix="/api")
    app.include_router(intelligence_router, prefix="/api")
    app.include_router(rot_router, prefix="/api")
    app.include_router(brief_router, prefix="/api")
    app.include_router(cockpit_router, prefix="/api")
    app.include_router(runs2_router, prefix="/api")
    app.include_router(doorway_router, prefix="/api")

    @app.get("/api/health")
    async def health():
        conn = get_conn()
        total = conn.execute("SELECT COUNT(*) FROM helicon_cubes").fetchone()[0]
        # "memories" is the name; "cubes" is a deprecated alias kept so the
        # dashboard, the app and fc/deploy-fc.sh keep working across the
        # rename. Drop it once every client reads "memories" (after Jul 20).
        return {"status": "ok", "memories": total, "cubes": total}

    @app.post("/mcp")
    async def remote_mcp(request: Request):
        """Stateless MCP-over-HTTP for remote agents.

        This boundary is disabled unless it has its own token. It deliberately
        exposes the agent workflow only; local maintenance tools that can write
        files or mutate the store in bulk stay on the stdio transport.
        """
        if not mcp_token:
            return JSONResponse(
                status_code=503,
                content={"error": "remote MCP is disabled; set HELICON_MCP_TOKEN"},
            )
        if len(mcp_token) < 32:
            return JSONResponse(
                status_code=503,
                content={"error": "HELICON_MCP_TOKEN must be at least 32 characters"},
            )

        supplied = request.headers.get("Authorization", "")
        expected = f"Bearer {mcp_token}"
        if not hmac.compare_digest(supplied, expected):
            return JSONResponse(
                status_code=401,
                content={"error": "unauthorized"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        content_length = request.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > _MAX_MCP_REQUEST_BYTES:
                    return JSONResponse(status_code=413, content={"error": "request too large"})
            except ValueError:
                return JSONResponse(status_code=400, content={"error": "invalid content length"})

        body = await request.body()
        if len(body) > _MAX_MCP_REQUEST_BYTES:
            return JSONResponse(status_code=413, content={"error": "request too large"})
        try:
            message = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                },
            )

        from helicon.mcp_server import REMOTE_TOOL_NAMES, handle_rpc_message
        async with mcp_lock:
            response = handle_rpc_message(
                message, get_conn(), allowed_tool_names=REMOTE_TOOL_NAMES,
            )
        if response is None:
            return Response(status_code=202)
        return JSONResponse(
            content=response,
            headers={"Cache-Control": "no-store"},
        )

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    # `static/` is gitignored (Cloud Shell / deploy copy web/dist there);
    # web/dist is now build output rather than a committed fossil. When neither
    # exists the API still serves — only the dashboard needs building — and the
    # unbuilt case says so instead of 404ing on every path, which is the one
    # thing the committed bundle was hiding.
    static_dir = _resolve_web_dir(repo_root)
    if static_dir:
        app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

        @app.get("/{path:path}")
        async def serve_spa(path: str):
            file_path = os.path.join(static_dir, path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(os.path.join(static_dir, "index.html"))
    else:
        @app.get("/{path:path}")
        async def dashboard_not_built(path: str):
            from fastapi.responses import HTMLResponse
            return HTMLResponse(
                "<h1>Dashboard not built</h1>"
                "<p>The API is running; the web bundle is build output and is "
                "not committed.</p>"
                "<pre>cd web &amp;&amp; npm install &amp;&amp; npm run build</pre>"
                "<p>Then restart <code>helicon serve</code>. "
                "The API itself is live at <a href='/api/health'>/api/health</a>.</p>",
                status_code=503)

    return app


app = create_app()
