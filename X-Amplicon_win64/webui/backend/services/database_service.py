"""Database registry service wrappers for the Web UI backend."""

from __future__ import annotations

from typing import Any

from src.core.database_registry import (
    check_database,
    list_databases,
    register_database,
)

from webui.backend.models.database import DatabaseRegistrationRequest


def list_database_records(*, registry_path: str | None = None, include_hash: bool = False) -> list[dict[str, Any]]:
    """List known database records."""

    return list_databases(registry_path=registry_path, include_builtin=True, include_hash=include_hash)


def check_database_record(
    database: str,
    *,
    registry_path: str | None = None,
    include_hash: bool = False,
) -> dict[str, Any]:
    """Check one database record or path."""

    return check_database(database, registry_path=registry_path, include_builtin=True, include_hash=include_hash)


def register_database_record(payload: DatabaseRegistrationRequest) -> dict[str, Any]:
    """Register one local database."""

    return register_database(
        payload.name,
        payload.path,
        version=payload.version,
        taxonomy_format=payload.taxonomy_format,
        database_type=payload.database_type,
        registry_path=payload.registry_path,
        aliases=payload.aliases,
        roles=payload.roles,
        sha256=payload.sha256,
        compute_hash=payload.compute_hash,
        require_exists=not payload.allow_missing,
        overwrite=payload.overwrite,
    )
