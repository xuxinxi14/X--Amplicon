"""Database management API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from webui.backend.models.database import DatabaseCheckRequest, DatabaseRegistrationRequest
from webui.backend.services.database_service import (
    check_database_record,
    list_database_records,
    register_database_record,
)

router = APIRouter(prefix="/databases", tags=["databases"])


@router.get("")
def get_databases(
    registry_path: str | None = None,
    include_hash: bool = Query(default=False),
) -> list[dict[str, object]]:
    return list_database_records(registry_path=registry_path, include_hash=include_hash)


@router.post("")
def post_database(payload: DatabaseRegistrationRequest) -> dict[str, object]:
    try:
        return register_database_record(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{database}/check")
def post_database_check(database: str, payload: DatabaseCheckRequest | None = None) -> dict[str, object]:
    payload = payload or DatabaseCheckRequest()
    return check_database_record(
        database,
        registry_path=payload.registry_path,
        include_hash=payload.include_hash,
    )
