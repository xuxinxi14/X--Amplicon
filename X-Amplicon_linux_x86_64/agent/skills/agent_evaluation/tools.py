"""Static evaluation tools for the X-Amplicon agent layer."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CASES_PATH = Path(__file__).with_name("test_cases.yaml")


def _load_cases(cases_path: str | None = None) -> list[dict[str, Any]]:
    path = Path(cases_path).expanduser() if cases_path else DEFAULT_CASES_PATH
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    with path.resolve().open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}
    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("Evaluation cases file must contain a 'cases' list.")
    return [case for case in cases if isinstance(case, dict)]


def list_agent_eval_cases(cases_path: str | None = None) -> dict[str, Any]:
    """List static agent evaluation cases."""

    cases = _load_cases(cases_path)
    return {
        "case_count": len(cases),
        "cases": [
            {
                "id": case.get("id"),
                "description": case.get("description", ""),
            }
            for case in cases
        ],
    }


def inspect_optional_skill_dependencies() -> dict[str, Any]:
    """Report availability of optional skill dependencies."""

    packages = {
        "biopython": "Bio",
        "llama-index": "llama_index",
        "deepeval": "deepeval",
        "ragas": "ragas",
        "opentelemetry-api": "opentelemetry",
        "opentelemetry-sdk": "opentelemetry.sdk",
    }
    availability = {}
    for package_name, import_name in packages.items():
        try:
            availability[package_name] = importlib.util.find_spec(import_name) is not None
        except ModuleNotFoundError:
            availability[package_name] = False
    return {
        "available": availability,
        "missing": [package for package, ok in availability.items() if not ok],
    }


def run_agent_eval_cases(
    cases_path: str | None = None,
    output_path: str = "run_logs/agent_evaluation_report.json",
) -> dict[str, Any]:
    """Run static registry and prompt checks for the agent."""

    from agent.agent import SYSTEM_PROMPT
    from agent.tools import get_tool_schemas

    cases = _load_cases(cases_path)
    available_tools = {schema["function"]["name"] for schema in get_tool_schemas()}
    prompt_text = SYSTEM_PROMPT.lower()

    results: list[dict[str, Any]] = []
    for case in cases:
        missing_tools = [
            tool
            for tool in case.get("expected_tools", []) or []
            if tool not in available_tools
        ]
        missing_terms = [
            term
            for term in case.get("expected_prompt_terms", []) or []
            if str(term).lower() not in prompt_text
        ]
        passed = not missing_tools and not missing_terms
        results.append(
            {
                "id": case.get("id"),
                "description": case.get("description", ""),
                "passed": passed,
                "missing_tools": missing_tools,
                "missing_prompt_terms": missing_terms,
            }
        )

    report = {
        "case_count": len(results),
        "passed_count": sum(1 for result in results if result["passed"]),
        "failed_count": sum(1 for result in results if not result["passed"]),
        "dependency_status": inspect_optional_skill_dependencies(),
        "results": results,
    }

    destination = Path(output_path).expanduser()
    if not destination.is_absolute():
        destination = PROJECT_ROOT / destination
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False, default=str)
    report["output_path"] = str(destination)
    return report


def summarize_agent_evaluation_log(
    log_path: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Summarize Agent task/tool evaluation JSONL events."""

    from agent.evaluation_logger import summarize_evaluation_log

    return summarize_evaluation_log(log_path=log_path, limit=limit)


def export_agent_evaluation_log(
    output_path: str = "run_logs/agent_evaluation_log_export.json",
    log_path: str | None = None,
) -> dict[str, Any]:
    """Export Agent task/tool evaluation JSONL events to JSON."""

    from agent.evaluation_logger import export_evaluation_log

    return export_evaluation_log(output_path=output_path, log_path=log_path)


TOOL_DEFINITIONS = [
    {
        "name": "list_agent_eval_cases",
        "description": "List built-in static evaluation cases for X-Amplicon agent skills.",
        "parameters": {
            "type": "object",
            "properties": {
                "cases_path": {"type": "string", "description": "Optional YAML cases file."},
            },
            "required": [],
        },
        "fn": list_agent_eval_cases,
    },
    {
        "name": "inspect_optional_skill_dependencies",
        "description": "Check whether optional skill dependencies are installed.",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "fn": inspect_optional_skill_dependencies,
    },
    {
        "name": "run_agent_eval_cases",
        "description": "Run static agent registry and prompt checks and write a JSON report.",
        "parameters": {
            "type": "object",
            "properties": {
                "cases_path": {"type": "string", "description": "Optional YAML cases file."},
                "output_path": {"type": "string", "default": "run_logs/agent_evaluation_report.json"},
            },
            "required": [],
        },
        "fn": run_agent_eval_cases,
    },
    {
        "name": "summarize_agent_evaluation_log",
        "description": "Summarize Agent evaluation JSONL events for tasks, tool calls, errors, and recovery paths.",
        "parameters": {
            "type": "object",
            "properties": {
                "log_path": {"type": "string", "description": "Optional evaluation JSONL path."},
                "limit": {"type": "integer", "default": 20},
            },
            "required": [],
        },
        "fn": summarize_agent_evaluation_log,
    },
    {
        "name": "export_agent_evaluation_log",
        "description": "Export Agent evaluation JSONL events to a single JSON file.",
        "parameters": {
            "type": "object",
            "properties": {
                "output_path": {
                    "type": "string",
                    "default": "run_logs/agent_evaluation_log_export.json",
                },
                "log_path": {"type": "string", "description": "Optional evaluation JSONL path."},
            },
            "required": [],
        },
        "fn": export_agent_evaluation_log,
    },
]
