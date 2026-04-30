"""Job models for background Web UI tasks."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from webui.backend.models.common import WebUIBaseModel, utc_now_iso

JobStatus = Literal["queued", "checking", "running", "paused", "completed", "failed", "cancelled"]


class JobEvent(WebUIBaseModel):
    """One structured event emitted by the job manager."""

    time: str = Field(default_factory=utc_now_iso)
    job_id: str
    type: str = "status"
    stage: str = "job"
    status: str = "running"
    message: str = ""
    command: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class JobRecord(WebUIBaseModel):
    """Persisted background job state."""

    id: str
    project_id: str | None = None
    job_type: str
    status: JobStatus = "queued"
    command: list[str] = Field(default_factory=list)
    display_command: str = ""
    cwd: str = ""
    pid: int | None = None
    return_code: int | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    started_at: str | None = None
    completed_at: str | None = None
    log_path: str
    event_path: str
    message: str = ""
    error: str | None = None
