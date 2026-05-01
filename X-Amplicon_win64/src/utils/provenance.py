"""Runtime provenance helpers for X-Amplicon workflows."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from src.core.database_registry import check_database

PROVENANCE_SCHEMA_VERSION = "1.0"
DEFAULT_PACKAGE_DISTRIBUTIONS = {
    "biopython": "biopython",
    "click": "click",
    "deepeval": "deepeval",
    "llama-index": "llama-index",
    "litellm": "litellm",
    "numpy": "numpy",
    "opentelemetry-api": "opentelemetry-api",
    "opentelemetry-sdk": "opentelemetry-sdk",
    "pandas": "pandas",
    "plotly": "plotly",
    "pydantic": "pydantic",
    "pyyaml": "PyYAML",
    "ragas": "ragas",
    "rich": "rich",
    "scikit-bio": "scikit-bio",
    "scipy": "scipy",
}
_PATH_KEY_HINTS = (
    "path",
    "file",
    "dir",
    "fasta",
    "fastq",
    "table",
    "matrix",
    "taxonomy",
    "otutab",
    "sintax",
    "summary",
    "tree",
    "db",
    "database",
    "report",
)
_INPUT_ROLE_HINTS = (
    "input",
    "source",
    "metadata",
    "seq_dir",
    "read1",
    "read2",
    "reference",
    "database",
    "db",
    "template",
)
_OUTPUT_ROLE_HINTS = (
    "output",
    "result",
    "final",
    "export",
    "generated",
    "summary",
    "report",
    "table",
    "matrix",
)


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).isoformat()


def file_sha256(path: str, chunk_size: int = 1024 * 1024) -> str:
    """Calculate a SHA-256 hash for a file."""

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_file(path: str, *, include_hash: bool = True) -> dict[str, Any]:
    """Describe one filesystem path without raising when it is absent."""

    resolved_path = os.path.abspath(str(path))
    record: dict[str, Any] = {
        "path": resolved_path,
        "exists": os.path.exists(resolved_path),
    }
    if not record["exists"]:
        return record

    record["is_file"] = os.path.isfile(resolved_path)
    record["is_dir"] = os.path.isdir(resolved_path)
    try:
        stat = os.stat(resolved_path)
    except OSError as exc:
        record["error"] = str(exc)
        return record

    record["size_bytes"] = int(stat.st_size)
    record["modified_at"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
    if include_hash and os.path.isfile(resolved_path):
        try:
            record["sha256"] = file_sha256(resolved_path)
        except OSError as exc:
            record["sha256_error"] = str(exc)
    return record


def _run_git(project_root: str, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def get_git_info(project_root: str) -> dict[str, Any]:
    """Return git commit metadata for the project when available."""

    resolved_root = os.path.abspath(project_root)
    commit = _run_git(resolved_root, ["rev-parse", "HEAD"])
    branch = _run_git(resolved_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    status = _run_git(resolved_root, ["status", "--porcelain"])
    return {
        "project_root": resolved_root,
        "commit": commit,
        "branch": branch,
        "dirty": None if status is None else bool(status),
        "status_porcelain": status,
    }


def get_package_versions(
    distributions: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return installed versions for key Python distributions."""

    requested = distributions or DEFAULT_PACKAGE_DISTRIBUTIONS
    versions: dict[str, dict[str, Any]] = {}
    for display_name, distribution_name in requested.items():
        try:
            version = importlib.metadata.version(distribution_name)
        except importlib.metadata.PackageNotFoundError:
            versions[display_name] = {"installed": False, "version": None}
        else:
            versions[display_name] = {"installed": True, "version": version}
    return versions


def get_python_environment() -> dict[str, Any]:
    """Return Python and OS environment metadata."""

    return {
        "python_version": sys.version,
        "python_version_info": list(sys.version_info[:5]),
        "python_executable": os.path.abspath(sys.executable),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "system": platform.system(),
        "release": platform.release(),
        "packages": get_package_versions(),
    }


def get_executable_version(path: str | None, label: str) -> dict[str, Any]:
    """Best-effort executable version discovery."""

    if path is None:
        return {"label": label, "path": None, "exists": False, "version": None}

    resolved_path = os.path.abspath(str(path))
    record: dict[str, Any] = {
        "label": label,
        "path": resolved_path,
        "exists": os.path.isfile(resolved_path),
        "version": None,
    }
    if not record["exists"]:
        return record

    for args in (["--version"], ["-version"], ["version"]):
        try:
            result = subprocess.run(
                [resolved_path, *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            record["version_error"] = str(exc)
            continue

        text = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        if text:
            record["version"] = text.splitlines()[0].strip()
            record["version_command"] = [resolved_path, *args]
            record["version_returncode"] = result.returncode
            return record

    return record


def _looks_like_path(value: Any, key_path: str) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or "\n" in text or "\t" in text:
        return False
    lowered_key = key_path.lower()
    if any(hint in lowered_key for hint in _PATH_KEY_HINTS):
        return True
    if os.path.exists(os.path.abspath(text)):
        return True
    return False


def _infer_role(key_path: str) -> str:
    lowered = key_path.lower()
    if any(hint in lowered for hint in _INPUT_ROLE_HINTS):
        return "input"
    if any(hint in lowered for hint in _OUTPUT_ROLE_HINTS):
        return "output"
    return "file"


def iter_path_references(value: Any, prefix: str = "") -> Iterable[dict[str, Any]]:
    """Yield path-like string references from nested structures."""

    if isinstance(value, Mapping):
        for key, item in value.items():
            key_path = f"{prefix}.{key}" if prefix else str(key)
            yield from iter_path_references(item, key_path)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            key_path = f"{prefix}[{index}]"
            yield from iter_path_references(item, key_path)
    elif _looks_like_path(value, prefix):
        yield {
            "key": prefix,
            "role": _infer_role(prefix),
            **describe_file(str(value), include_hash=False),
        }


def _dedupe_file_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        key = (str(record.get("key", "")), str(record.get("path", "")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def build_step_provenance(summary_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build compact per-step provenance records from run summary steps."""

    step_records: list[dict[str, Any]] = []
    for step in summary_steps:
        details = step.get("details", {})
        step_record = {
            "name": step.get("name"),
            "description": step.get("description"),
            "status": step.get("status"),
            "started_at": step.get("started_at"),
            "completed_at": step.get("completed_at"),
            "duration_seconds": step.get("duration_seconds"),
            "error": step.get("error"),
            "file_references": _dedupe_file_records(iter_path_references(details, "details")),
            "details": details,
        }
        step_records.append({key: value for key, value in step_record.items() if value not in (None, [], {})})
    return step_records


def _collect_output_files(outputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    path_records = iter_path_references(outputs, "outputs")
    file_records: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for record in path_records:
        path = record.get("path")
        if not path or path in seen_paths:
            continue
        seen_paths.add(str(path))
        if os.path.isfile(str(path)):
            file_records.append(
                {
                    "key": record.get("key"),
                    "role": record.get("role"),
                    **describe_file(str(path), include_hash=True),
                }
            )
    return file_records


def _find_first_existing_path(value: Any, key_names: set[str]) -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in key_names and isinstance(item, str) and os.path.exists(os.path.abspath(item)):
                return os.path.abspath(item)
            hit = _find_first_existing_path(item, key_names)
            if hit is not None:
                return hit
    elif isinstance(value, (list, tuple)):
        for item in value:
            hit = _find_first_existing_path(item, key_names)
            if hit is not None:
                return hit
    return None


def build_database_records(
    effective_params: Mapping[str, Any],
    outputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe configured reference and annotation databases."""

    records: dict[str, Any] = {}
    reference_db = effective_params.get("reference_db")
    if reference_db:
        records["chimera_reference"] = check_database(
            str(reference_db),
            include_hash=True,
        )

    annotation_database = effective_params.get("annotation_database")
    taxonomy_record: dict[str, Any] = {"name": annotation_database}
    sintax_database_path = _find_first_existing_path(
        outputs or {},
        {"database_path"},
    )
    configured_database_path = effective_params.get("annotation_database_path")
    if isinstance(configured_database_path, str) and configured_database_path.strip():
        sintax_database_path = configured_database_path

    if annotation_database:
        taxonomy_record = check_database(
            str(annotation_database),
            include_hash=True,
        )
        if taxonomy_record.get("status") == "failed" and sintax_database_path is not None:
            taxonomy_record = {
                **check_database(sintax_database_path, include_hash=True),
                "configured_name": annotation_database,
            }
    if sintax_database_path is not None:
        taxonomy_record.setdefault("path", os.path.abspath(sintax_database_path))
    records["taxonomy_annotation"] = taxonomy_record
    return records


def _find_tool_path(
    effective_params: Mapping[str, Any],
    outputs: Mapping[str, Any],
    tool_name: str,
) -> str | None:
    param_key = f"{tool_name.lower()}_path"
    param_value = effective_params.get(param_key)
    if isinstance(param_value, str) and param_value.strip():
        return os.path.abspath(param_value)

    key_names = {tool_name.lower()}
    return _find_first_existing_path(outputs, key_names)


def build_provenance_record(
    *,
    project_root: str,
    summary: Mapping[str, Any],
    provenance_path: str,
    provenance_md_path: str | None = None,
) -> dict[str, Any]:
    """Build a machine-readable provenance record for a pipeline run."""

    effective_params = summary.get("effective_params", {})
    outputs = summary.get("outputs", {})
    outputs = summary.get("outputs", {})
    outputs_mapping = outputs if isinstance(outputs, Mapping) else {}
    effective_mapping = effective_params if isinstance(effective_params, Mapping) else {}
    tools = {
        "usearch": get_executable_version(
            _find_tool_path(effective_mapping, outputs_mapping, "usearch"),
            "USEARCH",
        ),
        "vsearch": get_executable_version(
            _find_tool_path(effective_mapping, outputs_mapping, "vsearch"),
            "VSEARCH",
        ),
    }
    params_source = effective_mapping.get("params_source")

    record = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "provenance_path": os.path.abspath(provenance_path),
        "provenance_md_path": None if provenance_md_path is None else os.path.abspath(provenance_md_path),
        "workflow": {
            "name": "X-Amplicon",
            "status": summary.get("status"),
            "started_at": summary.get("started_at"),
            "completed_at": summary.get("completed_at"),
            "failed_step": summary.get("failed_step"),
            "error": summary.get("error"),
            "summary_path": summary.get("summary_path"),
            "sample_ids": summary.get("sample_ids", []),
            "sample_count": len(summary.get("sample_ids", []))
            if isinstance(summary.get("sample_ids"), list)
            else None,
        },
        "project": get_git_info(project_root),
        "runtime": get_python_environment(),
        "tools": tools,
        "databases": build_database_records(effective_mapping, outputs_mapping),
        "effective_params": effective_params,
        "parameter_source": (
            None
            if not isinstance(params_source, str) or not params_source.strip()
            else describe_file(params_source, include_hash=True)
        ),
        "steps": build_step_provenance(list(summary.get("steps", []))),
        "final_file_hashes": _collect_output_files(outputs_mapping),
    }
    return record


def write_json_record(record: Mapping[str, Any], path: str) -> str:
    """Write a JSON record with stable formatting."""

    resolved_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(resolved_path), exist_ok=True)
    with open(resolved_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(record, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return resolved_path


def write_provenance_markdown(record: Mapping[str, Any], path: str) -> str:
    """Write a concise human-readable provenance summary."""

    workflow = record.get("workflow", {})
    project = record.get("project", {})
    runtime = record.get("runtime", {})
    tools = record.get("tools", {})
    databases = record.get("databases", {})
    final_files = record.get("final_file_hashes", [])
    lines = [
        "# X-Amplicon Provenance",
        "",
        f"- Status: {workflow.get('status')}",
        f"- Started: {workflow.get('started_at')}",
        f"- Completed: {workflow.get('completed_at')}",
        f"- Git commit: {project.get('commit')}",
        f"- Git branch: {project.get('branch')}",
        f"- Git dirty: {project.get('dirty')}",
        f"- Python: {runtime.get('python_version')}",
        "",
        "## Tools",
        "",
    ]
    for name, tool in tools.items():
        lines.append(f"- {name}: {tool.get('path')} ({tool.get('version')})")

    lines.extend(["", "## Databases", ""])
    for name, database in databases.items():
        if isinstance(database, Mapping):
            lines.append(
                f"- {name}: {database.get('name') or database.get('path')} "
                f"size={database.get('size_bytes')} sha256={database.get('sha256')}"
            )

    lines.extend(["", "## Key Output Hashes", ""])
    for file_record in final_files:
        lines.append(
            f"- {file_record.get('key')}: {file_record.get('path')} "
            f"sha256={file_record.get('sha256')}"
        )

    resolved_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(resolved_path), exist_ok=True)
    with open(resolved_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")
    return resolved_path
