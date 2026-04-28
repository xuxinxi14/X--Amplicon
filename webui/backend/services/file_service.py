"""Safe local file access for the Web UI backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from webui.backend.config import get_project_root, resolve_path
from webui.backend.models.project import ProjectRecord
from webui.backend.models.settings import WebUISettings

TEXT_EXTENSIONS = {
    ".txt",
    ".tsv",
    ".csv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".md",
    ".html",
    ".htm",
    ".log",
}


def authorized_roots(
    *,
    project: ProjectRecord | None = None,
    settings: WebUISettings | None = None,
) -> list[Path]:
    """Return directories that the Web UI may read."""

    root = get_project_root()
    roots = [
        root,
        root / "work",
        root / "database",
        root / "databas",
        root / ".xamplicon_webui",
    ]
    if project is not None:
        roots.append(resolve_path(project.project_dir))
        roots.append(resolve_path(project.output_root, project.project_dir))
    if settings is not None:
        for directory in settings.authorized_dirs:
            if directory:
                roots.append(resolve_path(directory))
    deduped: list[Path] = []
    seen: set[str] = set()
    for item in roots:
        resolved = item.resolve()
        key = str(resolved).lower()
        if key not in seen:
            seen.add(key)
            deduped.append(resolved)
    return deduped


def resolve_authorized_path(
    path: str,
    *,
    project: ProjectRecord | None = None,
    settings: WebUISettings | None = None,
) -> Path:
    """Resolve and authorize a local path."""

    resolved = resolve_path(path)
    roots = authorized_roots(project=project, settings=settings)
    for root in roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise PermissionError(f"Path is outside authorized Web UI roots: {resolved}")


def read_text_file(
    path: str,
    *,
    project: ProjectRecord | None = None,
    settings: WebUISettings | None = None,
    max_bytes: int = 10_000_000,
) -> dict[str, Any]:
    """Read an authorized text file."""

    resolved = resolve_authorized_path(path, project=project, settings=settings)
    if not resolved.is_file():
        raise FileNotFoundError(f"File not found: {resolved}")
    if resolved.suffix.lower() not in TEXT_EXTENSIONS:
        raise ValueError(f"File type is not previewable as text: {resolved.suffix}")
    size = resolved.stat().st_size
    if size > max_bytes:
        raise ValueError(f"File is too large to preview ({size} bytes).")
    return {
        "path": str(resolved),
        "name": resolved.name,
        "size": size,
        "text": resolved.read_text(encoding="utf-8", errors="replace"),
    }


def list_directory(
    path: str,
    *,
    project: ProjectRecord | None = None,
    settings: WebUISettings | None = None,
) -> dict[str, Any]:
    """List an authorized directory without recursively scanning large trees."""

    resolved = resolve_authorized_path(path, project=project, settings=settings)
    if not resolved.is_dir():
        raise NotADirectoryError(f"Directory not found: {resolved}")
    entries = []
    for child in sorted(resolved.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        stat = child.stat()
        entries.append(
            {
                "name": child.name,
                "path": str(child),
                "is_dir": child.is_dir(),
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
        )
    return {"path": str(resolved), "entries": entries}
