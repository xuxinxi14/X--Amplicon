"""Read-only local retrieval tools for X-Amplicon agent sessions."""

from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATTERNS = ["*.md", "*.py", "*.yaml", "*.yml", "*.json", "*.txt", "*.tsv"]
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    ".tools",
    ".pip-tmp",
    ".pip-work",
    "bin",
    "databas",
    "seq",
    "work",
}


def _resolve_root(root: str | None = None) -> Path:
    base = Path(root).expanduser() if root else PROJECT_ROOT
    return base.resolve()


def _safe_resolve(path: str | os.PathLike[str], root: Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path is outside the allowed root: {resolved}") from exc
    return resolved


def _is_excluded(path: Path, root: Path, include_generated: bool) -> bool:
    if include_generated:
        return False
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in DEFAULT_EXCLUDED_DIRS for part in relative_parts)


def _matches_patterns(path: Path, patterns: list[str]) -> bool:
    name = path.name
    relative = str(path).replace("\\", "/")
    return any(fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(relative, pattern) for pattern in patterns)


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9_./\\-]+", text)]


def _read_text(path: Path, max_chars: int) -> tuple[str, bool]:
    data = path.read_text(encoding="utf-8", errors="replace")
    truncated = len(data) > max_chars
    if truncated:
        data = data[:max_chars]
    return data, truncated


def _snippets(text: str, query_tokens: set[str], max_snippets: int = 3) -> list[str]:
    snippets: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(token in lowered for token in query_tokens):
            compact = " ".join(line.split())
            snippets.append(compact[:240])
            if len(snippets) >= max_snippets:
                break
    return snippets


def search_project_files(
    query: str,
    root: str | None = None,
    include_patterns: list[str] | None = None,
    max_results: int = 10,
    include_generated: bool = False,
    max_file_size: int = 1_000_000,
) -> dict[str, Any]:
    """Search local project files with a small deterministic lexical scorer."""

    search_root = _resolve_root(root)
    patterns = include_patterns or DEFAULT_PATTERNS
    query_tokens = set(_tokenize(query))
    if not query_tokens:
        raise ValueError("query must contain at least one searchable token")

    scored: list[dict[str, Any]] = []
    for path in search_root.rglob("*"):
        if not path.is_file():
            continue
        if _is_excluded(path, search_root, include_generated):
            continue
        if not _matches_patterns(path, patterns):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > max_file_size:
            continue

        try:
            text, truncated = _read_text(path, max_chars=max_file_size)
        except OSError:
            continue

        relative = path.relative_to(search_root).as_posix()
        haystack = f"{relative}\n{text}".lower()
        score = 0
        for token in query_tokens:
            if token in relative.lower():
                score += 5
            score += haystack.count(token)
        if score <= 0:
            continue

        scored.append(
            {
                "path": relative,
                "score": score,
                "size_bytes": size,
                "truncated": truncated,
                "snippets": _snippets(text, query_tokens),
            }
        )

    scored.sort(key=lambda item: (-int(item["score"]), str(item["path"])))
    return {
        "query": query,
        "root": str(search_root),
        "results": scored[: max(1, max_results)],
        "result_count": len(scored),
        "used_llama_index": False,
    }


def read_project_file(
    path: str,
    root: str | None = None,
    max_chars: int = 20_000,
) -> dict[str, Any]:
    """Read a UTF-8 text file under the project root."""

    search_root = _resolve_root(root)
    resolved = _safe_resolve(path, search_root)
    if not resolved.is_file():
        raise FileNotFoundError(f"Project file not found: {resolved}")
    text, truncated = _read_text(resolved, max_chars=max(1, max_chars))
    return {
        "path": resolved.relative_to(search_root).as_posix(),
        "root": str(search_root),
        "size_bytes": resolved.stat().st_size,
        "truncated": truncated,
        "content": text,
    }


def read_analysis_summary(final_dir: str = "work/06_final") -> dict[str, Any]:
    """Read a completed pipeline run summary if it exists."""

    root = PROJECT_ROOT
    final_path = _safe_resolve(final_dir, root)
    summary_path = final_path / "run_summary.json"
    if not summary_path.is_file():
        return {
            "exists": False,
            "final_dir": str(final_path),
            "summary_path": str(summary_path),
            "message": "run_summary.json was not found.",
        }

    with summary_path.open("r", encoding="utf-8") as fh:
        summary = json.load(fh)

    steps = summary.get("steps", [])
    failed_steps = []
    if isinstance(steps, list):
        failed_steps = [
            step.get("name") or step.get("step")
            for step in steps
            if isinstance(step, dict) and str(step.get("status", "")).lower() == "failed"
        ]

    return {
        "exists": True,
        "final_dir": str(final_path),
        "summary_path": str(summary_path),
        "status": summary.get("status"),
        "failed_steps": [step for step in failed_steps if step],
        "top_level_keys": sorted(summary.keys()),
        "summary": summary,
    }


def find_output_artifacts(
    final_dir: str = "work/06_final",
    pattern: str = "*",
    max_results: int = 100,
) -> dict[str, Any]:
    """List generated output files under a final results directory."""

    root = PROJECT_ROOT
    final_path = _safe_resolve(final_dir, root)
    if not final_path.exists():
        return {
            "exists": False,
            "final_dir": str(final_path),
            "artifacts": [],
            "message": "Final output directory was not found.",
        }

    artifacts: list[dict[str, Any]] = []
    for path in final_path.rglob(pattern):
        if not path.is_file():
            continue
        relative = path.relative_to(final_path).as_posix()
        artifacts.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "modified_time": path.stat().st_mtime,
            }
        )

    artifacts.sort(key=lambda item: str(item["path"]))
    return {
        "exists": True,
        "final_dir": str(final_path),
        "pattern": pattern,
        "artifacts": artifacts[: max(1, max_results)],
        "artifact_count": len(artifacts),
    }


def preview_llama_index_documents(
    root: str | None = None,
    include_patterns: list[str] | None = None,
    max_documents: int = 20,
    include_generated: bool = False,
) -> dict[str, Any]:
    """Load a bounded set of project files through LlamaIndex when available."""

    try:
        from llama_index.core import SimpleDirectoryReader
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "llama-index is not installed. Install requirements-skills.txt to use this tool."
        ) from exc

    search_root = _resolve_root(root)
    patterns = include_patterns or DEFAULT_PATTERNS
    selected_files: list[str] = []
    for path in search_root.rglob("*"):
        if not path.is_file():
            continue
        if _is_excluded(path, search_root, include_generated):
            continue
        if not _matches_patterns(path, patterns):
            continue
        selected_files.append(str(path))
        if len(selected_files) >= max(1, max_documents):
            break

    reader = SimpleDirectoryReader(input_files=selected_files)
    documents = reader.load_data()
    previews = []
    for document in documents[: max(1, max_documents)]:
        text = getattr(document, "text", "") or ""
        metadata = getattr(document, "metadata", {}) or {}
        previews.append(
            {
                "metadata": metadata,
                "text_preview": text[:500],
                "text_length": len(text),
            }
        )

    return {
        "root": str(search_root),
        "selected_file_count": len(selected_files),
        "document_count": len(documents),
        "documents": previews,
        "used_llama_index": True,
    }


TOOL_DEFINITIONS = [
    {
        "name": "search_project_files",
        "description": (
            "Search local X-Amplicon project files using a bounded read-only lexical search. "
            "Use this for README, manuscript, params, source-code, and run-output questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "root": {"type": "string", "description": "Optional project root override."},
                "include_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional glob patterns such as *.md or *.json.",
                },
                "max_results": {"type": "integer", "default": 10},
                "include_generated": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include normally excluded generated or large-data directories.",
                },
                "max_file_size": {"type": "integer", "default": 1000000},
            },
            "required": ["query"],
        },
        "fn": search_project_files,
    },
    {
        "name": "read_project_file",
        "description": "Read a UTF-8 text file under the X-Amplicon project root.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path under the project root."},
                "root": {"type": "string", "description": "Optional project root override."},
                "max_chars": {"type": "integer", "default": 20000},
            },
            "required": ["path"],
        },
        "fn": read_project_file,
    },
    {
        "name": "read_analysis_summary",
        "description": "Read work/06_final/run_summary.json from a completed or failed pipeline run.",
        "parameters": {
            "type": "object",
            "properties": {
                "final_dir": {"type": "string", "default": "work/06_final"},
            },
            "required": [],
        },
        "fn": read_analysis_summary,
    },
    {
        "name": "find_output_artifacts",
        "description": "List generated files under a final output directory such as work/06_final.",
        "parameters": {
            "type": "object",
            "properties": {
                "final_dir": {"type": "string", "default": "work/06_final"},
                "pattern": {"type": "string", "default": "*"},
                "max_results": {"type": "integer", "default": 100},
            },
            "required": [],
        },
        "fn": find_output_artifacts,
    },
    {
        "name": "preview_llama_index_documents",
        "description": (
            "Use optional LlamaIndex SimpleDirectoryReader to preview project files "
            "as documents. Requires llama-index from requirements-skills.txt."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "root": {"type": "string", "description": "Optional project root override."},
                "include_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional glob patterns such as *.md or *.json.",
                },
                "max_documents": {"type": "integer", "default": 20},
                "include_generated": {"type": "boolean", "default": False},
            },
            "required": [],
        },
        "fn": preview_llama_index_documents,
    },
]
