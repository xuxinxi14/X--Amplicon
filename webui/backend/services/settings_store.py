"""Persistent Web UI settings store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from webui.backend.config import ensure_state_dir
from webui.backend.models.settings import WebUISettings
from webui.backend.services.json_store import read_json, write_json


def settings_path() -> Path:
    """Return the settings JSON path."""

    return ensure_state_dir() / "settings.json"


def load_settings() -> WebUISettings:
    """Load persisted settings or return defaults."""

    raw = read_json(settings_path(), {})
    if not isinstance(raw, dict):
        raw = {}
    return WebUISettings(**raw)


def save_settings(settings: WebUISettings) -> WebUISettings:
    """Persist settings."""

    write_json(settings_path(), settings.model_dump(mode="json"))
    return settings


def update_settings(patch: dict[str, Any]) -> WebUISettings:
    """Merge a partial settings payload into the current settings."""

    current = load_settings().model_dump(mode="json")
    current.update({key: value for key, value in patch.items() if value is not None})
    return save_settings(WebUISettings(**current))
