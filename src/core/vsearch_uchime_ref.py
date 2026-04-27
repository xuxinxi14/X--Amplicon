"""Reference-based chimera filtering workflow based on VSEARCH uchime_ref."""

from __future__ import annotations

import os
import shutil
from typing import Any, Dict, Optional

from src.utils.command_runner import run_command

from .database_registry import resolve_database_record
from .workflow_common import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_VSEARCH_WINDOWS_PATH,
    ensure_input_fasta,
    load_config_data,
    reorder_fasta_by_template,
    resolve_executable,
    validate_threads,
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_RDP_REFERENCE_DB = os.path.join(PROJECT_ROOT, "databas", "rdp_16s_v18.fa")
FALLBACK_VSEARCH_UCHIME_REF_DEFAULTS = {
    "reference_db": DEFAULT_RDP_REFERENCE_DB,
    "chimera_mode": "ref",
}


def _coerce_chimera_mode(value: Any) -> str:
    if isinstance(value, bool):
        return "ref" if value else "none"
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"ref", "reference", "uchime_ref"}:
            return "ref"
        if normalized in {"none", "off", "skip", "copy"}:
            return "none"
        if normalized in {"1", "true", "yes", "y", "on"}:
            return "ref"
        if normalized in {"0", "false", "no", "n", "off"}:
            return "none"
    raise ValueError("chimera_mode must be one of: ref, none.")


def _normalize_text_file_to_lf(path: str) -> None:
    with open(path, "r", encoding="utf-8", newline=None) as source:
        content = source.read()
    with open(path, "w", encoding="ascii", newline="\n") as destination:
        destination.write(content.replace("\r\n", "\n").replace("\r", "\n"))


def load_vsearch_uchime_ref_defaults(
    config_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Load VSEARCH uchime_ref defaults from config.yaml."""

    resolved_config_path = os.path.abspath(config_path or DEFAULT_CONFIG_PATH)
    default_config_path = os.path.abspath(DEFAULT_CONFIG_PATH)

    if not os.path.exists(resolved_config_path):
        if resolved_config_path == default_config_path:
            return dict(FALLBACK_VSEARCH_UCHIME_REF_DEFAULTS)
        raise FileNotFoundError(f"Config file not found: {resolved_config_path}")

    config_data = load_config_data(resolved_config_path)
    defaults = config_data.get("vsearch_uchime_ref_defaults", {})

    reference_db = defaults.get(
        "reference_db", FALLBACK_VSEARCH_UCHIME_REF_DEFAULTS["reference_db"]
    )
    raw_chimera_mode = defaults.get("chimera_mode")
    if raw_chimera_mode is None and "chimera_filter" in defaults:
        raw_chimera_mode = defaults["chimera_filter"]
    if raw_chimera_mode is None:
        raw_chimera_mode = FALLBACK_VSEARCH_UCHIME_REF_DEFAULTS["chimera_mode"]

    return {
        "reference_db": str(reference_db),
        "chimera_mode": _coerce_chimera_mode(raw_chimera_mode),
    }


def resolve_vsearch_executable(vsearch_path: Optional[str] = None) -> str:
    """Resolve a usable VSEARCH executable path."""

    return resolve_executable(
        executable_name="vsearch",
        configured_path=vsearch_path,
        windows_default_path=DEFAULT_VSEARCH_WINDOWS_PATH,
        label="VSEARCH",
    )


def _resolve_reference_db(
    reference_db: Optional[str],
    config_path: Optional[str],
) -> str:
    if reference_db is None:
        resolved_reference_db = load_vsearch_uchime_ref_defaults(config_path)[
            "reference_db"
        ]
    else:
        resolved_reference_db = reference_db

    try:
        database_record = resolve_database_record(
            str(resolved_reference_db),
            require_exists=True,
            include_hash=False,
        )
    except KeyError:
        absolute_reference_db = os.path.abspath(str(resolved_reference_db))
        if not os.path.isfile(absolute_reference_db):
            raise FileNotFoundError(
                f"Reference database file not found: {absolute_reference_db}"
            )
    else:
        absolute_reference_db = str(database_record["path"])

    return absolute_reference_db


def _resolve_chimera_mode(
    chimera_mode: Optional[str],
    config_path: Optional[str],
) -> str:
    if chimera_mode is None:
        return load_vsearch_uchime_ref_defaults(config_path)["chimera_mode"]
    return _coerce_chimera_mode(chimera_mode)


def run_vsearch_uchime_ref(
    input_fasta: str,
    output_dir: str,
    threads: int = 1,
    reference_db: Optional[str] = None,
    chimera_mode: Optional[str] = None,
    order_template_fasta: Optional[str] = None,
    config_path: Optional[str] = None,
    vsearch_path: Optional[str] = None,
    output_fasta_path: Optional[str] = None,
    command_timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Run reference-based chimera filtering with VSEARCH uchime_ref."""

    resolved_input_fasta = ensure_input_fasta(input_fasta)
    resolved_output_dir = os.path.abspath(output_dir)
    os.makedirs(resolved_output_dir, exist_ok=True)

    resolved_threads = validate_threads(threads)
    resolved_chimera_mode = _resolve_chimera_mode(chimera_mode, config_path)
    resolved_vsearch = resolve_vsearch_executable(vsearch_path)
    if resolved_chimera_mode == "ref":
        resolved_reference_db = _resolve_reference_db(reference_db, config_path)
    else:
        fallback_reference_db = (
            reference_db
            if reference_db is not None
            else load_vsearch_uchime_ref_defaults(config_path)["reference_db"]
        )
        resolved_reference_db = os.path.abspath(fallback_reference_db)

    final_output_path = os.path.join(resolved_output_dir, "01_result.fasta")
    chimeras_path = os.path.join(resolved_output_dir, "01_chimeras.fasta")
    uchime_report_path = os.path.join(resolved_output_dir, "01_uchime_report.tsv")
    reordered_output_path = os.path.join(resolved_output_dir, "02_reordered_result.fasta")

    print("[VSEARCH UCHIME_REF] Starting reference-based chimera workflow.")
    print(f"[VSEARCH UCHIME_REF] Input FASTA: {resolved_input_fasta}")
    print(f"[VSEARCH UCHIME_REF] Output directory: {resolved_output_dir}")
    if resolved_chimera_mode == "ref":
        print(f"[VSEARCH UCHIME_REF] Reference database: {resolved_reference_db}")
    else:
        print(
            f"[VSEARCH UCHIME_REF] Reference database: {resolved_reference_db} (not used)"
        )
    print(f"[VSEARCH UCHIME_REF] Chimera mode: {resolved_chimera_mode}")
    print(f"[VSEARCH UCHIME_REF] Threads: {resolved_threads}")
    print(f"[VSEARCH UCHIME_REF] VSEARCH executable: {resolved_vsearch}")
    if order_template_fasta is not None:
        print(f"[VSEARCH UCHIME_REF] Order template FASTA: {os.path.abspath(order_template_fasta)}")

    if resolved_chimera_mode == "ref":
        print("[VSEARCH UCHIME_REF] Step 1/1: Running uchime_ref.")
        run_command(
            [
                resolved_vsearch,
                "--uchime_ref",
                resolved_input_fasta,
                "--db",
                resolved_reference_db,
                "--nonchimeras",
                final_output_path,
                "--chimeras",
                chimeras_path,
                "--uchimeout",
                uchime_report_path,
                "--threads",
                str(resolved_threads),
            ],
            timeout=command_timeout,
        )
        _normalize_text_file_to_lf(final_output_path)
        _normalize_text_file_to_lf(chimeras_path)
        _normalize_text_file_to_lf(uchime_report_path)
        print(f"[VSEARCH UCHIME_REF] Step 1/1 complete: {final_output_path}")
    else:
        print(
            "[VSEARCH UCHIME_REF] Chimera mode is none. Copying input sequences to output."
        )
        shutil.copyfile(resolved_input_fasta, final_output_path)
        _normalize_text_file_to_lf(final_output_path)
        chimeras_path = None
        uchime_report_path = None

    effective_output_path = final_output_path
    if order_template_fasta is not None:
        resolved_template_fasta = ensure_input_fasta(order_template_fasta)
        reorder_summary = reorder_fasta_by_template(
            final_output_path,
            resolved_template_fasta,
            reordered_output_path,
        )
        effective_output_path = reordered_output_path
        print(
            "[VSEARCH UCHIME_REF] Reordered output by template: "
            f"{reorder_summary['matched_headers']} matched headers."
        )

    exported_output_path = effective_output_path
    if output_fasta_path:
        exported_output_path = os.path.abspath(output_fasta_path)
        parent_dir = os.path.dirname(exported_output_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        shutil.copyfile(effective_output_path, exported_output_path)
        print(
            f"[VSEARCH UCHIME_REF] Final output FASTA copied to: {exported_output_path}"
        )

    print("[VSEARCH UCHIME_REF] Workflow finished successfully.")

    return {
        "reference_db": resolved_reference_db,
        "chimera_mode": resolved_chimera_mode,
        "threads": resolved_threads,
        "command_timeout": command_timeout,
        "vsearch": resolved_vsearch,
        "result_fasta": exported_output_path,
        "nonchimeras": effective_output_path,
        "chimeras": chimeras_path,
        "uchime_report": uchime_report_path,
    }
