"""ASV denoising workflow based on USEARCH UNOISE3."""

from __future__ import annotations

import os
import shutil
from typing import Any, Dict, Optional

from src.utils.command_runner import run_command

from .workflow_common import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_USEARCH_WINDOWS_PATH,
    ensure_input_fasta,
    load_config_data,
    replace_header_text,
    resolve_executable,
    validate_positive_int,
    validate_threads,
)

FALLBACK_USEARCH_ASV_DEFAULTS = {"minsize": 10}


def load_usearch_asv_defaults(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load USEARCH ASV defaults from config.yaml."""

    resolved_config_path = os.path.abspath(config_path or DEFAULT_CONFIG_PATH)
    default_config_path = os.path.abspath(DEFAULT_CONFIG_PATH)

    if not os.path.exists(resolved_config_path):
        if resolved_config_path == default_config_path:
            return dict(FALLBACK_USEARCH_ASV_DEFAULTS)
        raise FileNotFoundError(f"Config file not found: {resolved_config_path}")

    config_data = load_config_data(resolved_config_path)
    defaults = config_data.get("usearch_asv_defaults", {})
    minsize = validate_positive_int(
        "minsize",
        defaults.get("minsize", FALLBACK_USEARCH_ASV_DEFAULTS["minsize"]),
    )
    return {"minsize": minsize}


def resolve_usearch_executable(usearch_path: Optional[str] = None) -> str:
    """Resolve a usable USEARCH executable path."""

    return resolve_executable(
        executable_name="usearch",
        configured_path=usearch_path,
        windows_default_path=DEFAULT_USEARCH_WINDOWS_PATH,
        label="USEARCH",
    )


def _resolve_minsize(minsize: Optional[int], config_path: Optional[str]) -> int:
    if minsize is None:
        return load_usearch_asv_defaults(config_path)["minsize"]
    return validate_positive_int("minsize", minsize)


def run_usearch_unoise3_denoising(
    input_fasta: str,
    output_dir: str,
    threads: int = 1,
    minsize: Optional[int] = None,
    config_path: Optional[str] = None,
    usearch_path: Optional[str] = None,
    asv_fasta_path: Optional[str] = None,
    command_timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Run USEARCH UNOISE3 to denoise sequences into ASVs."""

    resolved_input_fasta = ensure_input_fasta(input_fasta)
    resolved_output_dir = os.path.abspath(output_dir)
    os.makedirs(resolved_output_dir, exist_ok=True)

    resolved_threads = validate_threads(threads)
    resolved_minsize = _resolve_minsize(minsize, config_path)
    resolved_usearch = resolve_usearch_executable(usearch_path)

    zotus_path = os.path.join(resolved_output_dir, "01_zotus.fasta")
    asvs_path = os.path.join(resolved_output_dir, "02_asvs.fasta")
    asv_table_path = os.path.join(resolved_output_dir, "03_asv_table.tsv")

    print("[USEARCH ASV] Starting UNOISE3 ASV denoising workflow.")
    print(f"[USEARCH ASV] Input FASTA: {resolved_input_fasta}")
    print(f"[USEARCH ASV] Output directory: {resolved_output_dir}")
    print(f"[USEARCH ASV] Minimum abundance threshold: {resolved_minsize}")
    print(f"[USEARCH ASV] Threads: {resolved_threads}")
    print(f"[USEARCH ASV] USEARCH executable: {resolved_usearch}")

    print("[USEARCH ASV] Step 1/3: Denoising sequences with unoise3.")
    run_command(
        [
            resolved_usearch,
            "-unoise3",
            resolved_input_fasta,
            "-minsize",
            str(resolved_minsize),
            "-zotus",
            zotus_path,
        ],
        timeout=command_timeout,
    )
    print(f"[USEARCH ASV] Step 1/3 complete: {zotus_path}")

    print("[USEARCH ASV] Step 2/3: Renaming Zotu headers to ASV_.")
    asv_count = replace_header_text(zotus_path, asvs_path, "Zotu", "ASV_")
    if asv_count == 0:
        raise ValueError("UNOISE3 did not produce any ASVs.")
    print(f"[USEARCH ASV] Step 2/3 complete: {asvs_path} ({asv_count} ASVs)")

    print("[USEARCH ASV] Step 3/3: Building ASV abundance table with otutab.")
    run_command(
        [
            resolved_usearch,
            "-otutab",
            resolved_input_fasta,
            "-otus",
            asvs_path,
            "-otutabout",
            asv_table_path,
            "-threads",
            str(resolved_threads),
        ],
        timeout=command_timeout,
    )
    print(f"[USEARCH ASV] Step 3/3 complete: {asv_table_path}")

    final_asv_fasta_path = asvs_path
    if asv_fasta_path:
        final_asv_fasta_path = os.path.abspath(asv_fasta_path)
        parent_dir = os.path.dirname(final_asv_fasta_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        shutil.copyfile(asvs_path, final_asv_fasta_path)
        print(f"[USEARCH ASV] Final ASV FASTA copied to: {final_asv_fasta_path}")

    print("[USEARCH ASV] Workflow finished successfully.")

    return {
        "minsize": resolved_minsize,
        "threads": resolved_threads,
        "command_timeout": command_timeout,
        "usearch": resolved_usearch,
        "zotus": zotus_path,
        "asv_fasta": final_asv_fasta_path,
        "asv_table": asv_table_path,
    }
