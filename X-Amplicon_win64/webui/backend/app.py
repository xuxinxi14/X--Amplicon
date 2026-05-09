"""FastAPI application entry point for the X-Amplicon local Web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from webui.backend.api.agent import router as agent_router
from webui.backend.api.databases import router as databases_router
from webui.backend.api.files import router as files_router
from webui.backend.api.health import router as health_router
from webui.backend.api.jobs import router as jobs_router
from webui.backend.api.projects import router as projects_router
from webui.backend.api.results import router as results_router
from webui.backend.api.settings import router as settings_router
from webui.backend.config import APP_NAME, WEBUI_VERSION, get_project_root


def _frontend_dist_dir() -> Path:
    """Return the built frontend directory."""

    return get_project_root() / "webui" / "frontend" / "dist"


def _safe_dist_file(dist_dir: Path, requested_path: str) -> Path | None:
    """Resolve a static frontend file if it stays inside dist."""

    candidate = (dist_dir / requested_path).resolve()
    try:
        candidate.relative_to(dist_dir.resolve())
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


def _mount_frontend(app: FastAPI) -> None:
    """Serve the production React build when webui/frontend/dist exists."""

    dist_dir = _frontend_dist_dir()
    index_path = dist_dir / "index.html"
    assets_dir = dist_dir / "assets"
    if not index_path.is_file():
        return

    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def frontend_root() -> FileResponse:
        return FileResponse(index_path)

    @app.get("/{frontend_path:path}", include_in_schema=False)
    def frontend_fallback(frontend_path: str) -> FileResponse:
        if frontend_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found.")
        static_file = _safe_dist_file(dist_dir, frontend_path)
        if static_file is not None:
            return FileResponse(static_file)
        return FileResponse(index_path)


def create_app() -> FastAPI:
    """Create and configure the local Web UI backend."""

    app = FastAPI(
        title=APP_NAME,
        version=WEBUI_VERSION,
        description="Local browser interface for running and reviewing X-Amplicon analyses.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8765",
            "http://localhost:8765",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(projects_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(results_router, prefix="/api")
    app.include_router(databases_router, prefix="/api")
    app.include_router(files_router, prefix="/api")
    app.include_router(agent_router, prefix="/api")

    if _frontend_dist_dir().joinpath("index.html").is_file():
        _mount_frontend(app)
    else:
        @app.get("/")
        def root() -> dict[str, str]:
            return {
                "status": "ok",
                "app": APP_NAME,
                "message": (
                    "X-Amplicon Web UI backend is running. Build the frontend "
                    "with 'npm.cmd run build' in webui/frontend to serve the browser UI."
                ),
            }

    return app


app = create_app()
