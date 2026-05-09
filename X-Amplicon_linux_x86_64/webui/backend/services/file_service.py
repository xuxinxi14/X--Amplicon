"""Safe local file access for the Web UI backend."""

from __future__ import annotations

import html
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote, unquote, urlencode, urlsplit

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

HTML_LINK_ATTR_PATTERN = re.compile(
    r"(?P<prefix>\b(?:src|href)\s*=\s*)(?P<quote>[\"'])(?P<url>.*?)(?P=quote)",
    flags=re.IGNORECASE,
)
HTML_RAW_BLOCK_PATTERN = re.compile(
    r"<(?:script|style)\b.*?</(?:script|style)>",
    flags=re.IGNORECASE | re.DOTALL,
)


def _should_rewrite_html_url(url: str) -> bool:
    stripped = url.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    if (
        stripped.startswith("#")
        or stripped.startswith("/")
        or stripped.startswith("//")
        or lowered.startswith(("http:", "https:", "data:", "javascript:", "mailto:", "tel:"))
    ):
        return False
    return True


def _split_local_html_url(url: str) -> tuple[str, str]:
    if re.match(r"^[A-Za-z]:[\\/]", url):
        return url, ""
    parsed = urlsplit(url)
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return parsed.path, fragment


def rewrite_html_links_for_file_view(
    html_text: str,
    *,
    source_path: Path,
    project: ProjectRecord | None = None,
    settings: WebUISettings | None = None,
    route_prefix: str = "/api/files/view",
) -> str:
    """Rewrite local relative HTML links so nested reports work inside /api/files/view."""

    source_dir = source_path.parent.resolve()

    def replace(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        quote_char = match.group("quote")
        raw_url = html.unescape(match.group("url"))
        if not _should_rewrite_html_url(raw_url):
            return match.group(0)

        local_path, fragment = _split_local_html_url(raw_url)
        if not local_path:
            return match.group(0)

        target = Path(unquote(local_path))
        if not target.is_absolute():
            target = source_dir / target
        try:
            resolved = resolve_authorized_path(str(target.resolve()), project=project, settings=settings)
        except PermissionError:
            return match.group(0)

        query = {"path": str(resolved)}
        if project is not None:
            query["project_id"] = project.id
        rewritten = f"{route_prefix}?{urlencode(query, quote_via=quote)}{fragment}"
        return f"{prefix}{quote_char}{html.escape(rewritten, quote=True)}{quote_char}"

    parts: list[str] = []
    cursor = 0
    for block in HTML_RAW_BLOCK_PATTERN.finditer(html_text):
        parts.append(HTML_LINK_ATTR_PATTERN.sub(replace, html_text[cursor:block.start()]))
        parts.append(block.group(0))
        cursor = block.end()
    parts.append(HTML_LINK_ATTR_PATTERN.sub(replace, html_text[cursor:]))
    return "".join(parts)


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
