"""Shared Pydantic models for the Web UI backend."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now_iso() -> str:
    """Return the current UTC time in ISO-8601 format."""

    return datetime.now(timezone.utc).isoformat()


class WebUIBaseModel(BaseModel):
    """Base model that tolerates forward-compatible fields."""

    model_config = ConfigDict(extra="allow")


class StatusMessage(WebUIBaseModel):
    """Generic status response."""

    status: Literal["ok", "warning", "failed"] = "ok"
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class CommandSpec(WebUIBaseModel):
    """A subprocess command represented safely as an argument list."""

    args: list[str]
    display: str
    cwd: str
