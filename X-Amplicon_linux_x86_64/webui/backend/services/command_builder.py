"""Command construction for Web UI jobs."""

from __future__ import annotations

from pathlib import Path
import subprocess

from webui.backend.config import get_default_python_executable, get_process_script, get_project_root
from webui.backend.models.common import CommandSpec
from webui.backend.models.settings import WebUISettings


def _python(settings: WebUISettings | None = None) -> str:
    if settings and settings.python_executable:
        return settings.python_executable
    return get_default_python_executable()


def _display(args: list[str]) -> str:
    return subprocess.list2cmdline([str(arg) for arg in args])


def _spec(args: list[str], cwd: str | Path | None = None) -> CommandSpec:
    resolved_cwd = str(Path(cwd).resolve() if cwd else get_project_root())
    string_args = [str(arg) for arg in args]
    return CommandSpec(args=string_args, display=_display(string_args), cwd=resolved_cwd)


def check_pipeline_config(params_path: str, settings: WebUISettings | None = None) -> CommandSpec:
    return _spec([_python(settings), str(get_process_script()), "check-pipeline-config", "--params", params_path])


def run_pipeline_config(params_path: str, settings: WebUISettings | None = None) -> CommandSpec:
    return _spec([_python(settings), str(get_process_script()), "run-pipeline-config", "--params", params_path])


def visualization_suite(
    final_dir: str,
    *,
    output_format: str = "all",
    metadata: str | None = None,
    sample_id_col: str = "SampleID",
    group_col: str = "Group",
    color_palette: str | None = None,
    settings: WebUISettings | None = None,
) -> CommandSpec:
    args = [
        _python(settings),
        str(get_process_script()),
        "visualization-suite",
        "--final-dir",
        final_dir,
        "--format",
        output_format,
        "--sample-id-col",
        sample_id_col,
        "--group-col",
        group_col,
    ]
    if metadata:
        args.extend(["--metadata", metadata])
    if color_palette:
        args.extend(["--color-palette", color_palette])
    return _spec(args)


def differential_abundance(
    *,
    otutab: str,
    metadata: str,
    output_dir: str | None = None,
    taxonomy: str | None = None,
    comparisons: list[str] | None = None,
    reference_group: str | None = None,
    output_format: str = "html",
    group_col: str = "Group",
    sample_id_col: str = "SampleID",
    settings: WebUISettings | None = None,
) -> CommandSpec:
    args = [
        _python(settings),
        str(get_process_script()),
        "differential-abundance",
        "--otutab",
        otutab,
        "--metadata",
        metadata,
        "--format",
        output_format,
        "--group-col",
        group_col,
        "--sample-id-col",
        sample_id_col,
    ]
    if output_dir:
        args.extend(["--output-dir", output_dir])
    if taxonomy:
        args.extend(["--taxonomy", taxonomy])
    for comparison in comparisons or []:
        args.extend(["--compare", comparison])
    if reference_group:
        args.extend(["--reference-group", reference_group])
    return _spec(args)


def generate_report(final_dir: str, settings: WebUISettings | None = None) -> CommandSpec:
    return _spec([_python(settings), str(get_process_script()), "generate-report", "--final-dir", final_dir])


def list_databases(settings: WebUISettings | None = None, *, registry_path: str | None = None) -> CommandSpec:
    args = [_python(settings), str(get_process_script()), "list-databases"]
    if registry_path:
        args.extend(["--registry", registry_path])
    return _spec(args)


def check_database(
    database: str,
    settings: WebUISettings | None = None,
    *,
    registry_path: str | None = None,
    include_hash: bool = False,
) -> CommandSpec:
    args = [_python(settings), str(get_process_script()), "check-database", database]
    if registry_path:
        args.extend(["--registry", registry_path])
    if not include_hash:
        args.append("--no-hash")
    return _spec(args)


def register_database(
    *,
    name: str,
    path: str,
    settings: WebUISettings | None = None,
    registry_path: str | None = None,
) -> CommandSpec:
    args = [_python(settings), str(get_process_script()), "register-database", "--name", name, "--path", path]
    if registry_path:
        args.extend(["--registry", registry_path])
    return _spec(args)
