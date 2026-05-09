"""Persistent project registry for the Web UI backend."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from webui.backend.config import ensure_state_dir, get_project_root, resolve_path
from webui.backend.models.common import utc_now_iso
from webui.backend.models.project import ProjectCreate, ProjectRecord, ProjectUpdate
from webui.backend.services.json_store import read_json, write_json

PROJECTS_SCHEMA_VERSION = "1.0"


def projects_path() -> Path:
    """Return the projects JSON path."""

    return ensure_state_dir() / "projects.json"


def _load_payload() -> dict[str, Any]:
    payload = read_json(projects_path(), {"schema_version": PROJECTS_SCHEMA_VERSION, "projects": []})
    if not isinstance(payload, dict):
        payload = {"schema_version": PROJECTS_SCHEMA_VERSION, "projects": []}
    if not isinstance(payload.get("projects"), list):
        payload["projects"] = []
    return payload


def _save_projects(projects: list[ProjectRecord]) -> None:
    write_json(
        projects_path(),
        {
            "schema_version": PROJECTS_SCHEMA_VERSION,
            "projects": [project.model_dump(mode="json") for project in projects],
        },
    )


def _slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", text.strip()).strip("-._").lower()
    return slug or "project"


def list_projects() -> list[ProjectRecord]:
    """List known projects."""

    payload = _load_payload()
    projects: list[ProjectRecord] = []
    for raw in payload.get("projects", []):
        if isinstance(raw, dict):
            try:
                projects.append(ProjectRecord(**raw))
            except Exception:
                continue
    return sorted(projects, key=lambda item: item.updated_at, reverse=True)


def get_project(project_id: str) -> ProjectRecord:
    """Return one project or raise KeyError."""

    for project in list_projects():
        if project.id == project_id:
            return project
    raise KeyError(f"Project not found: {project_id}")


def create_project(payload: ProjectCreate) -> ProjectRecord:
    """Create and persist a project record."""

    name = payload.name.strip()
    if not name:
        raise ValueError("Project name cannot be empty.")
    project_id = f"{_slug(name)}-{uuid4().hex[:8]}"
    project_dir = payload.project_dir or str(get_project_root())
    resolved_project_dir = str(resolve_path(project_dir))
    record = ProjectRecord(
        id=project_id,
        name=name,
        project_dir=resolved_project_dir,
        output_root=payload.output_root or "work",
        analysis_type=payload.analysis_type or "16S rRNA",
    )
    projects = list_projects()
    projects.append(record)
    _save_projects(projects)
    return record


def update_project(project_id: str, patch: ProjectUpdate | dict[str, Any]) -> ProjectRecord:
    """Partially update a project record."""

    patch_data = patch.model_dump(exclude_unset=True, mode="json") if isinstance(patch, ProjectUpdate) else dict(patch)
    projects = list_projects()
    updated: ProjectRecord | None = None
    next_projects: list[ProjectRecord] = []
    for project in projects:
        if project.id != project_id:
            next_projects.append(project)
            continue
        raw = project.model_dump(mode="json")
        raw.update(
            {
                key: value
                for key, value in patch_data.items()
                if value is not None or key == "last_preflight_job_id"
            }
        )
        if "project_dir" in raw:
            raw["project_dir"] = str(resolve_path(str(raw["project_dir"])))
        raw["updated_at"] = utc_now_iso()
        updated = ProjectRecord(**raw)
        next_projects.append(updated)
    if updated is None:
        raise KeyError(f"Project not found: {project_id}")
    _save_projects(next_projects)
    return updated


def delete_project(project_id: str) -> None:
    """Remove one project record without deleting analysis outputs."""

    projects = list_projects()
    next_projects = [project for project in projects if project.id != project_id]
    if len(next_projects) == len(projects):
        raise KeyError(f"Project not found: {project_id}")
    _save_projects(next_projects)


def clear_projects() -> int:
    """Remove all project records without deleting analysis outputs."""

    count = len(list_projects())
    _save_projects([])
    return count
