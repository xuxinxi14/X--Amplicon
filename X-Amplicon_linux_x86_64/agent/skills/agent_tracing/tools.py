"""Trace utilities for agent tool calls."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TRACE_PATH = PROJECT_ROOT / "run_logs" / "agent_tool_trace.jsonl"
ENV_FILE = PROJECT_ROOT / ".env"


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


def _trace_path(trace_path: str | None = None) -> Path:
    configured = trace_path or os.getenv("X_AMPLICON_AGENT_TRACE_PATH") or _load_env_file_value(
        "X_AMPLICON_AGENT_TRACE_PATH"
    )
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()
    return DEFAULT_TRACE_PATH


def record_tool_trace_event(event: dict[str, Any], trace_path: str | None = None) -> dict[str, Any]:
    """Append one JSONL trace event.

    This helper is called by agent.tools.execute_tool as a best-effort hook.
    It is not exposed as an LLM tool.
    """

    path = _trace_path(trace_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        json.dump(event, fh, ensure_ascii=False, default=str)
        fh.write("\n")
    _record_opentelemetry_span(event)
    return {"trace_path": str(path), "event_id": event.get("event_id")}


def _record_opentelemetry_span(event: dict[str, Any]) -> None:
    """Emit an OpenTelemetry span when the optional package is installed."""

    try:
        from opentelemetry import trace
    except Exception:  # noqa: BLE001
        return

    try:
        tracer = trace.get_tracer("x_amplicon.agent")
        span_name = f"agent.tool.{event.get('tool', 'unknown')}"
        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute("x_amplicon.tool", str(event.get("tool", "unknown")))
            span.set_attribute("x_amplicon.status", str(event.get("status", "unknown")))
            span.set_attribute(
                "x_amplicon.duration_seconds",
                float(event.get("duration_seconds", 0.0) or 0.0),
            )
            if event.get("error"):
                span.set_attribute("x_amplicon.error", str(event.get("error")))
    except Exception:  # noqa: BLE001
        return


def _read_events(trace_path: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    path = _trace_path(trace_path)
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if limit is not None and limit > 0:
        return events[-limit:]
    return events


def summarize_agent_traces(trace_path: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Summarize recorded agent tool-call traces."""

    all_events = _read_events(trace_path)
    recent_events = all_events[-max(1, limit) :]
    status_counts = Counter(str(event.get("status", "unknown")) for event in all_events)
    tool_counts = Counter(str(event.get("tool", "unknown")) for event in all_events)
    durations = [
        float(event.get("duration_seconds"))
        for event in all_events
        if isinstance(event.get("duration_seconds"), (int, float))
    ]
    return {
        "trace_path": str(_trace_path(trace_path)),
        "event_count": len(all_events),
        "status_counts": dict(status_counts),
        "tool_counts": dict(tool_counts),
        "total_duration_seconds": round(sum(durations), 6),
        "recent_events": recent_events,
    }


def export_agent_traces(
    output_path: str = "run_logs/agent_tool_trace_export.json",
    trace_path: str | None = None,
) -> dict[str, Any]:
    """Export JSONL traces as one JSON document."""

    events = _read_events(trace_path)
    destination = Path(output_path).expanduser()
    if not destination.is_absolute():
        destination = PROJECT_ROOT / destination
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "trace_path": str(_trace_path(trace_path)),
        "event_count": len(events),
        "events": events,
    }
    with destination.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
    return {"output_path": str(destination), "event_count": len(events)}


TOOL_DEFINITIONS = [
    {
        "name": "summarize_agent_traces",
        "description": "Summarize JSONL trace events recorded for X-Amplicon agent tool calls.",
        "parameters": {
            "type": "object",
            "properties": {
                "trace_path": {"type": "string", "description": "Optional trace JSONL path."},
                "limit": {"type": "integer", "default": 20},
            },
            "required": [],
        },
        "fn": summarize_agent_traces,
    },
    {
        "name": "export_agent_traces",
        "description": "Export recorded JSONL tool-call traces to a single JSON file.",
        "parameters": {
            "type": "object",
            "properties": {
                "output_path": {"type": "string", "default": "run_logs/agent_tool_trace_export.json"},
                "trace_path": {"type": "string", "description": "Optional trace JSONL path."},
            },
            "required": [],
        },
        "fn": export_agent_traces,
    },
]
