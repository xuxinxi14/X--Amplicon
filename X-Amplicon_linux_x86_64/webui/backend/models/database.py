"""Database API models for the Web UI backend."""

from __future__ import annotations

from pydantic import Field

from webui.backend.models.common import WebUIBaseModel


class DatabaseCheckRequest(WebUIBaseModel):
    """Database check options."""

    include_hash: bool = False
    registry_path: str | None = None


class DatabaseRegistrationRequest(WebUIBaseModel):
    """Payload for registering a local reference database."""

    name: str
    path: str
    version: str | None = None
    taxonomy_format: str = "sintax"
    database_type: str = "taxonomy_annotation"
    registry_path: str | None = None
    aliases: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=lambda: ["taxonomy_annotation"])
    sha256: str | None = None
    compute_hash: bool = True
    allow_missing: bool = False
    overwrite: bool = False
