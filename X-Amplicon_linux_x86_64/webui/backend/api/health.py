"""Health-check endpoints for the local Web UI backend."""

from __future__ import annotations

from datetime import datetime, timezone
import sys

from fastapi import APIRouter

from webui.backend.config import APP_NAME, WEBUI_VERSION, get_project_root

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Return a lightweight backend status payload."""

    return {
        "status": "ok",
        "app": APP_NAME,
        "version": WEBUI_VERSION,
        "cwd": str(get_project_root()),
        "python": sys.executable,
        "time": datetime.now(timezone.utc).isoformat(),
    }
