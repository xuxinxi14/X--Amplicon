"""Result-index API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from webui.backend.models.results import ResultIndex
from webui.backend.models.project import ProjectRecord
from webui.backend.config import get_project_root
from webui.backend.services.project_store import get_project
from webui.backend.services.result_indexer import build_result_index

router = APIRouter(prefix="/results", tags=["results"])


@router.get("/{project_id}", response_model=ResultIndex)
def get_results(project_id: str) -> ResultIndex:
    if project_id in {"current", "__current__"}:
        root = get_project_root()
        return build_result_index(
            ProjectRecord(
                id="current",
                name="Current workspace",
                project_dir=str(root),
                output_root="work",
            )
        )
    try:
        project = get_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return build_result_index(project)
