"""Background job API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from webui.backend.models.job import JobRecord
from webui.backend.services.job_manager import manager

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobRecord])
def list_jobs(limit: int | None = Query(default=50, ge=1, le=200)) -> list[JobRecord]:
    return manager.list_jobs(limit=limit)


@router.get("/{job_id}", response_model=JobRecord)
def get_job(job_id: str) -> JobRecord:
    try:
        return manager.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{job_id}/logs")
def get_job_logs(job_id: str, tail: int | None = Query(default=None, ge=1)) -> dict[str, object]:
    try:
        return manager.get_logs(job_id, tail_lines=tail)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{job_id}/cancel", response_model=JobRecord)
def cancel_job(job_id: str) -> JobRecord:
    try:
        return manager.cancel_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
