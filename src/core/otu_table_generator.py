"""OTU/feature table generation using either USEARCH or VSEARCH."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from src.utils.command_runner import run_command

from .workflow_common import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_USEARCH_WINDOWS_PATH,
    DEFAULT_VSEARCH_WINDOWS_PATH,
    ensure_input_fasta,
    load_config_data,
    normalize_text_file_line_endings,
    resolve_executable,
    validate_threads,
)

FALLBACK_OTUTAB_DEFAULTS = {
    "method": "vsearch",
    "identity": 0.97,
}


def load_otutab_defaults(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load default OTU table generation settings from config.yaml."""

    resolved_config_path = os.path.abspath(config_path or DEFAULT_CONFIG_PATH)
    default_config_path = os.path.abspath(DEFAULT_CONFIG_PATH)

    if not os.path.exists(resolved_config_path):
        if resolved_config_path == default_config_path:
            return dict(FALLBACK_OTUTAB_DEFAULTS)
        raise FileNotFoundError(f"Config file not found: {resolved_config_path}")

    config_data = load_config_data(resolved_config_path)
    defaults = config_data.get("otutab_defaults", {})

    raw_method = defaults.get("method", FALLBACK_OTUTAB_DEFAULTS["method"])
    raw_identity = defaults.get("identity", FALLBACK_OTUTAB_DEFAULTS["identity"])

    method = _resolve_method(raw_method)

    try:
        identity = float(raw_identity)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid config value for otutab_defaults.identity.") from exc

    if not 0 < identity <= 1:
        raise ValueError("otutab_defaults.identity must be between 0 and 1.")

    return {"method": method, "identity": identity}


def _resolve_method(method: Optional[str]) -> str:
    if method is None:
        raise ValueError("method is required.")

    normalized = str(method).strip().lower()
    if normalized not in {"usearch", "vsearch"}:
        raise ValueError("method must be either 'usearch' or 'vsearch'.")

    return normalized


def _resolve_identity(identity: Optional[float], config_path: Optional[str]) -> float:
    if identity is None:
        resolved_identity = load_otutab_defaults(config_path)["identity"]
    else:
        try:
            resolved_identity = float(identity)
        except (TypeError, ValueError) as exc:
            raise ValueError("identity must be a number between 0 and 1.") from exc

    if not 0 < resolved_identity <= 1:
        raise ValueError("identity must be a number between 0 and 1.")

    return resolved_identity


def _resolve_usearch_executable(tool_path: Optional[str] = None) -> str:
    return resolve_executable(
        executable_name="usearch",
        configured_path=tool_path,
        windows_default_path=DEFAULT_USEARCH_WINDOWS_PATH,
        label="USEARCH",
    )


def _resolve_vsearch_executable(tool_path: Optional[str] = None) -> str:
    return resolve_executable(
        executable_name="vsearch",
        configured_path=tool_path,
        windows_default_path=DEFAULT_VSEARCH_WINDOWS_PATH,
        label="VSEARCH",
    )


def run_otutab_generation(
    input_fasta: str,
    representative_fasta: str,
    output_dir: str,
    method: str = "vsearch",
    threads: int = 1,
    identity: Optional[float] = None,
    config_path: Optional[str] = None,
    tool_path: Optional[str] = None,
    output_table_path: Optional[str] = None,
    command_timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Generate an OTU/feature table using USEARCH or VSEARCH."""

    resolved_input_fasta = ensure_input_fasta(input_fasta)
    resolved_representative_fasta = ensure_input_fasta(representative_fasta)
    resolved_output_dir = os.path.abspath(output_dir)
    os.makedirs(resolved_output_dir, exist_ok=True)

    resolved_method = _resolve_method(method)
    resolved_threads = validate_threads(threads)
    resolved_identity = _resolve_identity(identity, config_path)
    default_output_path = os.path.join(resolved_output_dir, "01_otutab.tsv")
    final_output_table_path = os.path.abspath(output_table_path or default_output_path)
    parent_dir = os.path.dirname(final_output_table_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    print("[OTUTAB] Starting OTU/feature table generation.")
    print(f"[OTUTAB] Input FASTA: {resolved_input_fasta}")
    print(f"[OTUTAB] Representative FASTA: {resolved_representative_fasta}")
    print(f"[OTUTAB] Output table: {final_output_table_path}")
    print(f"[OTUTAB] Method: {resolved_method}")
    print(f"[OTUTAB] Threads: {resolved_threads}")

    if resolved_method == "usearch":
        resolved_tool = _resolve_usearch_executable(tool_path)
        print(f"[OTUTAB] USEARCH executable: {resolved_tool}")
        run_command(
            [
                resolved_tool,
                "-otutab",
                resolved_input_fasta,
                "-otus",
                resolved_representative_fasta,
                "-threads",
                str(resolved_threads),
                "-otutabout",
                final_output_table_path,
            ],
            timeout=command_timeout,
        )
    else:
        resolved_tool = _resolve_vsearch_executable(tool_path)
        print(f"[OTUTAB] VSEARCH executable: {resolved_tool}")
        print(f"[OTUTAB] Identity threshold: {resolved_identity}")
        run_command(
            [
                resolved_tool,
                "--usearch_global",
                resolved_input_fasta,
                "--db",
                resolved_representative_fasta,
                "--id",
                f"{resolved_identity:.4f}",
                "--threads",
                str(resolved_threads),
                "--otutabout",
                final_output_table_path,
            ],
            timeout=command_timeout,
        )
        # VSEARCH on Windows may emit CRLF; normalize to LF for downstream tools.
        normalize_text_file_line_endings(final_output_table_path, line_ending="\n")

    print("[OTUTAB] OTU/feature table generation finished successfully.")

    return {
        "method": resolved_method,
        "threads": resolved_threads,
        "identity": resolved_identity if resolved_method == "vsearch" else None,
        "tool": resolved_tool,
        "command_timeout": command_timeout,
        "input_fasta": resolved_input_fasta,
        "representative_fasta": resolved_representative_fasta,
        "otutab": final_output_table_path,
    }
