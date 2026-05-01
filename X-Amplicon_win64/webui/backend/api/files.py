"""Safe local file API routes."""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from webui.backend.services.file_service import (
    list_directory,
    read_text_file,
    resolve_authorized_path,
    rewrite_html_links_for_file_view,
)
from webui.backend.services.project_store import get_project
from webui.backend.services.settings_store import load_settings

router = APIRouter(prefix="/files", tags=["files"])


def _optional_project(project_id: str | None):
    if not project_id:
        return None
    try:
        return get_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/read")
def read_file(path: str, project_id: str | None = None) -> dict[str, object]:
    try:
        return read_text_file(path, project=_optional_project(project_id), settings=load_settings())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/list")
def list_files(path: str, project_id: str | None = None) -> dict[str, object]:
    try:
        return list_directory(path, project=_optional_project(project_id), settings=load_settings())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/download")
def download_file(path: str, project_id: str | None = None, filename: str | None = Query(default=None)):
    try:
        resolved = resolve_authorized_path(path, project=_optional_project(project_id), settings=load_settings())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {resolved}")
    return FileResponse(str(resolved), filename=filename or resolved.name)


@router.get("/view")
def view_file(path: str, project_id: str | None = None):
    project = _optional_project(project_id)
    settings = load_settings()
    try:
        resolved = resolve_authorized_path(path, project=project, settings=settings)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {resolved}")
    media_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
    if media_type == "text/html":
        html_text = resolved.read_text(encoding="utf-8", errors="replace")
        rewritten = rewrite_html_links_for_file_view(
            html_text,
            source_path=resolved,
            project=project,
            settings=settings,
        )
        return HTMLResponse(rewritten)
    return FileResponse(str(resolved), media_type=media_type)
