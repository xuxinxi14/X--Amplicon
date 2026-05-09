"""Build structured Run Monitor progress from existing job records."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from webui.backend.models.job import JobProgressResponse, JobProgressStep, JobRecord
from webui.backend.services.project_store import get_project
from webui.backend.services.result_indexer import final_dir_for_project

PIPELINE_STEP_KEYS = [
    "validate_inputs",
    "merge_pairs",
    "filter_reads",
    "dereplicate_sequences",
    "generate_features",
    "remove_chimeras",
    "build_raw_feature_table",
    "annotate_taxonomy",
    "filter_final_outputs",
    "generate_phylogenetic_tree",
    "generate_analysis_outputs",
]

ACTIVE_STATUSES = {"queued", "checking", "running", "in_progress"}


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_seconds(started_at: str | None, completed_at: str | None) -> float | None:
    start = _parse_time(started_at)
    end = _parse_time(completed_at)
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds())


def _read_events(job: JobRecord, warnings: list[str]) -> list[dict[str, Any]]:
    path = Path(job.event_path)
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                warnings.append("Some job events could not be parsed; using the readable events only.")
                continue
            if isinstance(raw, dict):
                events.append(raw)
    except OSError as exc:
        warnings.append(f"Could not read job events: {exc}")
    return events


def _read_run_summary(job: JobRecord, warnings: list[str]) -> dict[str, Any] | None:
    if not job.project_id:
        return None
    try:
        project = get_project(job.project_id)
    except KeyError:
        warnings.append("Project record was not found; using job events only.")
        return None
    path = final_dir_for_project(project) / "run_summary.json"
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(f"Could not read run_summary.json; using job events only: {exc}")
        return None
    return raw if isinstance(raw, dict) else None


def _events_by_stage(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        stage = _as_text(event.get("stage")) or "job"
        grouped.setdefault(stage, []).append(event)
    return grouped


def _planned_stages(events: list[dict[str, Any]]) -> list[str]:
    stages: list[str] = []
    for event in events:
        details = event.get("details")
        steps = details.get("steps") if isinstance(details, dict) else None
        if isinstance(steps, list):
            for stage in steps:
                if isinstance(stage, str) and stage not in stages:
                    stages.append(stage)
    for event in events:
        stage = _as_text(event.get("stage"))
        if stage and stage != "job" and stage not in stages:
            stages.append(stage)
    return stages


def _step_from_job(job: JobRecord, key: str | None = None) -> JobProgressStep:
    return JobProgressStep(
        key=key or job.job_type,
        status=job.status,
        message=job.message,
        error=job.error,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=_duration_seconds(job.started_at, job.completed_at),
        source="job",
    )


def _step_from_events(key: str, events: list[dict[str, Any]]) -> JobProgressStep:
    if not events:
        return JobProgressStep(key=key, status="pending", source="event")
    latest = events[-1]
    started_at = next(
        (_as_text(event.get("time")) for event in events if _as_text(event.get("status")) in ACTIVE_STATUSES),
        None,
    )
    completed_at = next(
        (
            _as_text(event.get("time"))
            for event in reversed(events)
            if _as_text(event.get("status")) in {"completed", "failed", "cancelled"}
        ),
        None,
    )
    status = _as_text(latest.get("status")) or "pending"
    message = _as_text(latest.get("message"))
    details = latest.get("details")
    error = None
    if isinstance(details, dict):
        error = _as_text(details.get("error")) or None
    if status == "failed" and not error:
        error = message or None
    return JobProgressStep(
        key=key,
        status=status,
        message=message,
        error=error,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=_duration_seconds(started_at, completed_at),
        source="event",
    )


def _summary_status(status: Any) -> str:
    value = _as_text(status) or "pending"
    return "running" if value == "in_progress" else value


def _step_from_summary(raw: dict[str, Any]) -> JobProgressStep:
    key = _as_text(raw.get("name")) or _as_text(raw.get("key"))
    started_at = _as_text(raw.get("started_at")) or None
    completed_at = _as_text(raw.get("completed_at")) or None
    duration = raw.get("duration_seconds")
    return JobProgressStep(
        key=key,
        status=_summary_status(raw.get("status")),
        message=_as_text(raw.get("description")) or _as_text(raw.get("message")),
        error=_as_text(raw.get("error")) or None,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration if isinstance(duration, (int, float)) else _duration_seconds(started_at, completed_at),
        source="run_summary",
    )


def _summary_pipeline_steps(summary: dict[str, Any]) -> list[JobProgressStep]:
    raw_steps = [step for step in summary.get("steps", []) if isinstance(step, dict)]
    by_key = {_as_text(step.get("name")) or _as_text(step.get("key")): step for step in raw_steps}
    steps: list[JobProgressStep] = []
    for key in PIPELINE_STEP_KEYS:
        raw = by_key.get(key)
        if raw is not None:
            steps.append(_step_from_summary(raw))
        elif raw_steps:
            steps.append(JobProgressStep(key=key, status="pending", source="run_summary"))
    for raw in raw_steps:
        key = _as_text(raw.get("name")) or _as_text(raw.get("key"))
        if key and key not in PIPELINE_STEP_KEYS:
            steps.append(_step_from_summary(raw))
    return steps


def _latest_event_stage(events: list[dict[str, Any]], statuses: set[str]) -> str | None:
    for event in reversed(events):
        status = _as_text(event.get("status"))
        stage = _as_text(event.get("stage"))
        if status in statuses and stage and stage != "job":
            return stage
    return None


def _failed_summary_message(summary: dict[str, Any] | None, failed_step: str | None) -> str:
    if not summary:
        return ""
    for step in summary.get("steps", []):
        if isinstance(step, dict) and (_as_text(step.get("name")) or _as_text(step.get("key"))) == failed_step:
            return _as_text(step.get("error")) or _as_text(step.get("message"))
    return _as_text(summary.get("error"))


def build_job_progress(job: JobRecord) -> JobProgressResponse:
    """Return progress without parsing free-text CLI logs."""

    warnings: list[str] = []
    events = _read_events(job, warnings)
    grouped = _events_by_stage(events)
    summary = _read_run_summary(job, warnings)

    if job.job_type == "preflight":
        steps = [_step_from_events("preflight", grouped.get("job", [])) if events else _step_from_job(job, "preflight")]
    elif job.job_type == "full_analysis":
        stages = _planned_stages(events)
        steps = _summary_pipeline_steps(summary) if summary else []
        if not steps and ("pipeline" in stages or "pipeline" in grouped):
            steps.append(_step_from_events("pipeline", grouped.get("pipeline", [])))
        for stage in stages:
            if stage != "pipeline":
                steps.append(_step_from_events(stage, grouped.get(stage, [])))
        if not steps:
            steps = [_step_from_job(job, "full_analysis")]
    else:
        stage_events = grouped.get(job.job_type) or grouped.get("job", [])
        steps = [_step_from_events(job.job_type, stage_events) if stage_events else _step_from_job(job)]

    failed_step = _as_text(summary.get("failed_step")) if summary else None
    if not failed_step:
        failed_step = _latest_event_stage(events, {"failed", "cancelled"})
    current_step = _as_text(summary.get("current_step")) if summary else None
    if not current_step and not failed_step:
        current_step = _latest_event_stage(events, ACTIVE_STATUSES)

    failed_message = _failed_summary_message(summary, failed_step)
    message = failed_message or job.error or job.message

    return JobProgressResponse(
        job_id=job.id,
        status=job.status,
        current_step=current_step or None,
        failed_step=failed_step or None,
        message=message,
        steps=steps,
        warnings=warnings,
    )
