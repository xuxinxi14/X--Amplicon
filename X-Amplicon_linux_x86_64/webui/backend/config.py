"""Shared configuration helpers for the X-Amplicon Web UI backend."""

from __future__ import annotations

from pathlib import Path
import os
import sys

APP_NAME = "X-Amplicon Web UI"
WEBUI_VERSION = "0.1.0"


def get_project_root() -> Path:
    """Return the repository root for a source checkout."""

    return Path(__file__).resolve().parents[2]


def get_state_dir() -> Path:
    """Return the local Web UI state directory."""

    return get_project_root() / ".xamplicon_webui"


def ensure_state_dir() -> Path:
    """Create and return the local Web UI state directory."""

    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_jobs_dir() -> Path:
    """Create and return the local Web UI job-state directory."""

    jobs_dir = ensure_state_dir() / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    return jobs_dir


def resolve_path(path: str | Path, base_dir: str | Path | None = None) -> Path:
    """Resolve a user path relative to a project/base directory or the repo root."""

    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    base = Path(base_dir).expanduser() if base_dir else get_project_root()
    return (base / candidate).resolve()


def get_default_python_executable() -> str:
    """Return the preferred Python executable for Web UI subprocesses."""

    root = get_project_root()
    if os.name == "nt":
        bundled_python = root / ".tools" / "python-3.13.13-amd64" / "python.exe"
        if bundled_python.is_file():
            return str(bundled_python)

        venv_python = root / ".venv" / "Scripts" / "python.exe"
        if venv_python.is_file():
            return str(venv_python)

    venv_python = root / ".venv" / "bin" / "python"
    if venv_python.is_file():
        return str(venv_python)

    for bundled_python in sorted((root / ".tools").glob("python*/bin/python")):
        if bundled_python.is_file():
            return str(bundled_python)

    return sys.executable or "python"


def get_process_script() -> Path:
    """Return the process.py entry point path."""

    return get_project_root() / "process.py"
