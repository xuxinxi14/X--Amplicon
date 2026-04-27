"""Evaluation logging helpers for the X-Amplicon agent layer.

The logger writes JSONL events that can be analyzed later for Agent
benchmarking, error-recovery studies, and tool-use statistics. Logging is
designed to be called best-effort by runtime code; callers should never let a
logging failure interrupt an analysis run.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVALUATION_LOG_PATH = PROJECT_ROOT / "run_logs" / "agent_evaluation_log.jsonl"
ENV_FILE = PROJECT_ROOT / ".env"
EVALUATION_LOG_ENV_KEY = "X_AMPLICON_AGENT_EVAL_LOG_PATH"
AGENT_EVALUATION_SCHEMA_VERSION = "1.0"

_ERROR_CLASSIFIERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "missing_metadata",
        "confirm_metadata_path",
        (
            "metadata_path not found",
            "metadata file not found",
            "missing metadata",
            "metadata table is empty",
        ),
    ),
    (
        "missing_seq_dir",
        "confirm_seq_dir",
        (
            "seq_dir not found",
            "sequence directory not found",
            "fastq directory not found",
        ),
    ),
    (
        "missing_executable",
        "configure_external_executable",
        (
            "usearch executable not found",
            "vsearch executable not found",
            "external executable not found",
            "unable to locate usearch",
            "unable to locate vsearch",
            "missing executable",
        ),
    ),
    (
        "missing_reference_database",
        "check_database_registry_or_path",
        (
            "reference_db not found",
            "reference database not found",
            "database fasta file not found",
            "annotation database not found",
        ),
    ),
    (
        "bad_tree_path",
        "remove_or_fix_beta_tree_path",
        (
            "beta_tree_path not found",
            "tree file not found",
            "invalid tree path",
            "phylogenetic tree file not found",
        ),
    ),
    (
        "missing_fastq_pairs",
        "fix_metadata_or_read_suffixes",
        (
            "missing paired-end",
            "missing paired end",
            "missing fastq",
            "read pair",
            "read1_suffix",
            "read2_suffix",
        ),
    ),
    (
        "database_config_error",
        "fix_database_registry",
        (
            "database registry",
            "databases.yaml",
            "registered database",
            "database check failed",
            "database configuration",
        ),
    ),
    (
        "llm_unavailable",
        "configure_llm_or_use_cli",
        (
            "no llm api key",
            "no api key found",
            "no api key is configured",
            "natural-language agent orchestration is disabled",
            "offline mode",
            "无 llm",
            "未配置 llm api key",
        ),
    ),
    (
        "max_tool_rounds",
        "refine_request_or_reduce_tool_loop",
        (
            "maximum number of tool-call rounds",
            "max_tool_rounds",
        ),
    ),
)


def _load_env_file_value(key: str) -> str:
    if not ENV_FILE.is_file():
        return ""
    try:
        with ENV_FILE.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                if name.strip().lstrip("\ufeff") == key:
                    return value.strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""


def resolve_evaluation_log_path(log_path: str | None = None) -> Path:
    """Resolve the JSONL evaluation log path."""

    configured = (
        log_path
        or os.getenv(EVALUATION_LOG_ENV_KEY)
        or _load_env_file_value(EVALUATION_LOG_ENV_KEY)
    )
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()
    return DEFAULT_EVALUATION_LOG_PATH


def summarize_json_value(value: Any, *, max_text: int = 500) -> Any:
    """Return a compact JSON-friendly representation for logs."""

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        compact = " ".join(value.split())
        return compact if len(compact) <= max_text else compact[: max_text - 3] + "..."
    if isinstance(value, (list, tuple)):
        items = [summarize_json_value(item, max_text=max_text) for item in value[:20]]
        if len(value) > 20:
            items.append(f"... {len(value) - 20} more items")
        return items
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 30:
                compact["..."] = f"{len(value) - 30} more keys"
                break
            compact[str(key)] = summarize_json_value(item, max_text=max_text)
        return compact

    text = repr(value)
    return text if len(text) <= max_text else text[: max_text - 3] + "..."


def classify_error(error_text: Any) -> dict[str, str | None]:
    """Classify common Agent/tool errors into evaluation-friendly labels."""

    text = " ".join(str(error_text or "").lower().split())
    if not text:
        return {"error_type": None, "recovery_path": None}

    for error_type, recovery_path, patterns in _ERROR_CLASSIFIERS:
        if any(pattern in text for pattern in patterns):
            return {"error_type": error_type, "recovery_path": recovery_path}

    return {"error_type": "tool_error", "recovery_path": "inspect_tool_error"}


def append_evaluation_event(
    event: dict[str, Any],
    log_path: str | None = None,
) -> dict[str, Any]:
    """Append one event to the evaluation JSONL log."""

    path = resolve_evaluation_log_path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": AGENT_EVALUATION_SCHEMA_VERSION,
        **event,
    }
    with path.open("a", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, default=str)
        fh.write("\n")
    return {"log_path": str(path), "event_id": payload.get("event_id")}


def record_tool_evaluation_event(
    *,
    tool_name: str,
    raw_arguments: dict[str, Any],
    resolved_arguments: dict[str, Any] | None,
    result: dict[str, Any],
    start_time: float,
    log_path: str | None = None,
) -> dict[str, Any]:
    """Record one tool-call evaluation event."""

    duration_seconds = time.perf_counter() - start_time
    status = str(result.get("status", "unknown"))
    event: dict[str, Any] = {
        "event_id": uuid.uuid4().hex,
        "event_type": "tool_call",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "status": status,
        "duration_seconds": round(duration_seconds, 6),
        "arguments": summarize_json_value(raw_arguments),
        "result": summarize_json_value(result),
    }
    if resolved_arguments is not None and resolved_arguments != raw_arguments:
        event["resolved_arguments"] = summarize_json_value(resolved_arguments)

    if status == "error":
        error = result.get("error", "")
        event["error"] = summarize_json_value(error)
        event.update(classify_error(error))

    append_evaluation_event(event, log_path=log_path)
    return event


def record_task_evaluation_event(
    *,
    task_id: str,
    user_message: str,
    status: str,
    start_time: float,
    turn_index: int,
    round_count: int,
    tool_call_count: int,
    tool_error_count: int = 0,
    failure_reason: str | None = None,
    assistant_reply: str | None = None,
    model: str | None = None,
    llm_available: bool | None = None,
    error_types: list[str] | None = None,
    recovery_paths: list[str] | None = None,
    log_path: str | None = None,
) -> dict[str, Any]:
    """Record one user-task evaluation event."""

    duration_seconds = time.perf_counter() - start_time
    event: dict[str, Any] = {
        "event_id": uuid.uuid4().hex,
        "event_type": "user_task",
        "task_id": task_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "duration_seconds": round(duration_seconds, 6),
        "turn_index": turn_index,
        "round_count": round_count,
        "tool_call_count": tool_call_count,
        "tool_error_count": tool_error_count,
        "recovery_required": tool_error_count > 0,
        "user_message_summary": summarize_json_value(user_message),
    }
    if assistant_reply is not None:
        event["assistant_reply_summary"] = summarize_json_value(assistant_reply)
    if model:
        event["model"] = model
    if llm_available is not None:
        event["llm_available"] = bool(llm_available)
    if error_types:
        event["error_types"] = sorted(set(str(item) for item in error_types if item))
    if recovery_paths:
        event["recovery_paths"] = sorted(set(str(item) for item in recovery_paths if item))
    if failure_reason:
        event["failure_reason"] = summarize_json_value(failure_reason)
        classification = classify_error(failure_reason)
        event["error_type"] = classification["error_type"]
        event["recovery_path"] = classification["recovery_path"]

    append_evaluation_event(event, log_path=log_path)
    return event


def read_evaluation_events(
    log_path: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Read valid JSONL events from the evaluation log."""

    path = resolve_evaluation_log_path(log_path)
    if not path.is_file():
        return []

    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)

    if limit is not None and limit > 0:
        return events[-limit:]
    return events


def summarize_evaluation_log(
    log_path: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Summarize recorded Agent evaluation events."""

    events = read_evaluation_events(log_path)
    recent_events = [] if limit <= 0 else events[-limit:]
    event_type_counts = Counter(str(event.get("event_type", "unknown")) for event in events)
    status_counts = Counter(str(event.get("status", "unknown")) for event in events)
    tool_counts = Counter(
        str(event.get("tool", "unknown"))
        for event in events
        if event.get("event_type") == "tool_call"
    )
    error_type_counts = Counter(
        str(event.get("error_type"))
        for event in events
        if event.get("error_type")
    )
    recovery_path_counts = Counter(
        str(event.get("recovery_path"))
        for event in events
        if event.get("recovery_path")
    )

    task_events = [event for event in events if event.get("event_type") == "user_task"]
    tool_events = [event for event in events if event.get("event_type") == "tool_call"]
    task_durations = [
        float(event.get("duration_seconds"))
        for event in task_events
        if isinstance(event.get("duration_seconds"), (int, float))
    ]
    tool_durations = [
        float(event.get("duration_seconds"))
        for event in tool_events
        if isinstance(event.get("duration_seconds"), (int, float))
    ]

    return {
        "log_path": str(resolve_evaluation_log_path(log_path)),
        "event_count": len(events),
        "event_type_counts": dict(event_type_counts),
        "status_counts": dict(status_counts),
        "tool_counts": dict(tool_counts),
        "error_type_counts": dict(error_type_counts),
        "recovery_path_counts": dict(recovery_path_counts),
        "task_count": len(task_events),
        "tool_call_count": len(tool_events),
        "task_success_count": sum(1 for event in task_events if event.get("status") == "success"),
        "task_failure_count": sum(
            1
            for event in task_events
            if event.get("status") in {"failed", "max_rounds", "no_llm"}
        ),
        "recovery_required_task_count": sum(
            1 for event in task_events if event.get("recovery_required")
        ),
        "total_task_duration_seconds": round(sum(task_durations), 6),
        "total_tool_duration_seconds": round(sum(tool_durations), 6),
        "recent_events": recent_events,
    }


def export_evaluation_log(
    output_path: str = "run_logs/agent_evaluation_log_export.json",
    log_path: str | None = None,
) -> dict[str, Any]:
    """Export JSONL evaluation events as one JSON document."""

    events = read_evaluation_events(log_path)
    destination = Path(output_path).expanduser()
    if not destination.is_absolute():
        destination = PROJECT_ROOT / destination
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "log_path": str(resolve_evaluation_log_path(log_path)),
        "event_count": len(events),
        "summary": summarize_evaluation_log(log_path=log_path, limit=0),
        "events": events,
    }
    with destination.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
    return {"output_path": str(destination), "event_count": len(events)}
