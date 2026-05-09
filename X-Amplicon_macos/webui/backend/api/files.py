"""Safe local file API routes."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response

from webui.backend.services.file_service import (
    list_directory,
    read_text_file,
    resolve_authorized_path,
    rewrite_html_links_for_file_view,
)
from webui.backend.services.project_store import get_project
from webui.backend.services.settings_store import load_settings

router = APIRouter(prefix="/files", tags=["files"])

TABLE_EXPORT_MEDIA_TYPES = {
    "png": "image/png",
    "svg": "image/svg+xml",
    "pdf": "application/pdf",
}


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


@router.get("/table-export")
def export_table(
    path: str,
    format: str = Query(default="png"),
    project_id: str | None = None,
    max_rows: int = Query(default=80, ge=1, le=200),
):
    output_format = format.lower()
    if output_format not in TABLE_EXPORT_MEDIA_TYPES:
        raise HTTPException(status_code=400, detail="Table export format must be one of: png, svg, pdf.")
    project = _optional_project(project_id)
    settings = load_settings()
    try:
        resolved = resolve_authorized_path(path, project=project, settings=settings)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if resolved.suffix.lower() not in {".tsv", ".csv", ".txt"}:
        raise HTTPException(status_code=400, detail="Only TSV, CSV, or TXT tables can be exported.")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {resolved}")

    try:
        import pandas as pd
        import plotly.graph_objects as go
        import plotly.io as pio

        separator = "," if resolved.suffix.lower() == ".csv" else "\t"
        table = pd.read_csv(resolved, sep=separator, dtype=str, keep_default_na=False, nrows=max_rows)
        fig = go.Figure(
            data=[
                go.Table(
                    header={"values": [str(column) for column in table.columns], "fill_color": "#eef3f7", "align": "left"},
                    cells={
                        "values": [table[column].astype(str).tolist() for column in table.columns],
                        "fill_color": "white",
                        "align": "left",
                    },
                )
            ]
        )
        width = max(800, min(2400, max(1, len(table.columns)) * 150))
        height = max(320, min(2400, 110 + (len(table.index) + 1) * 30))
        content = pio.to_image(fig, format=output_format, width=width, height=height, scale=2)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Could not export table. Kaleido may be missing: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not export table: {exc}") from exc

    filename = f"{resolved.stem}.{output_format}"
    return Response(
        content=content,
        media_type=TABLE_EXPORT_MEDIA_TYPES[output_format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pick")
def pick_path(kind: str = Query(default="file", pattern="^(file|directory)$"), title: str | None = None) -> dict[str, str | None]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Local file picker is not available: {exc}") from exc

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if kind == "directory":
            selected = filedialog.askdirectory(parent=root, title=title or "Select folder")
        else:
            selected = filedialog.askopenfilename(parent=root, title=title or "Select file")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not open local file picker: {exc}") from exc
    finally:
        if root is not None:
            root.destroy()

    return {"path": str(Path(selected).resolve()) if selected else None}


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
