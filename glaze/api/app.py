import os
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from glaze.config import load_config
from glaze.db import init_db
from glaze.qwen import set_cache_db
from glaze.triage import init_triage_table

_conn: sqlite3.Connection | None = None
_config: dict = {}


def get_conn() -> sqlite3.Connection:
    return _conn


def get_config() -> dict:
    return _config


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _conn, _config
    _config = load_config()
    db_path = _config.get("db_path", "data/glaze.db")
    _conn = init_db(db_path)
    set_cache_db(_conn)
    init_triage_table(_conn)
    yield
    if _conn:
        _conn.close()


def create_app() -> FastAPI:
    app = FastAPI(title="GLAZE", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    password = os.environ.get("GLAZE_PASSWORD")
    if password:
        @app.middleware("http")
        async def auth_middleware(request: Request, call_next):
            if request.url.path.startswith("/api/"):
                token = request.headers.get("Authorization", "").replace("Bearer ", "")
                if token != password:
                    return JSONResponse(status_code=401, content={"error": "unauthorized"})
            return await call_next(request)

    from glaze.api.cubes import router as cubes_router
    from glaze.api.review import router as review_router
    from glaze.api.score import router as score_router
    from glaze.api.patterns import router as patterns_router
    from glaze.api.audit import router as audit_router
    from glaze.api.connectors import router as connectors_router
    from glaze.api.graph import router as graph_router
    from glaze.api.search import router as search_router
    from glaze.api.sessions import router as sessions_router
    from glaze.api.triage import router as triage_router
    from glaze.api.projects import router as projects_router
    from glaze.api.eval import router as eval_router
    from glaze.api.playbooks import router as playbooks_router
    from glaze.api.consolidation import router as consolidation_router
    from glaze.api.tokens import router as tokens_router

    app.include_router(cubes_router, prefix="/api")
    app.include_router(review_router, prefix="/api")
    app.include_router(score_router, prefix="/api")
    app.include_router(patterns_router, prefix="/api")
    app.include_router(audit_router, prefix="/api")
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

    @app.get("/api/health")
    async def health():
        conn = get_conn()
        total = conn.execute("SELECT COUNT(*) FROM glaze_cubes").fetchone()[0]
        return {"status": "ok", "cubes": total}

    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
    if os.path.isdir(static_dir):
        app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

        @app.get("/{path:path}")
        async def serve_spa(path: str):
            file_path = os.path.join(static_dir, path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(os.path.join(static_dir, "index.html"))

    return app


app = create_app()
