"""OTU clustering workflow based on USEARCH cluster_otus."""

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
    resolve_executable,
    validate_positive_int,
    validate_threads,
)

FALLBACK_USEARCH_OTU_DEFAULTS = {"minsize": 10}


def load_usearch_otu_defaults(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load USEARCH OTU defaults from config.yaml."""

    resolved_config_path = os.path.abspath(config_path or DEFAULT_CONFIG_PATH)
    default_config_path = os.path.abspath(DEFAULT_CONFIG_PATH)

    if not os.path.exists(resolved_config_path):
        if resolved_config_path == default_config_path:
            return dict(FALLBACK_USEARCH_OTU_DEFAULTS)
        raise FileNotFoundError(f"Config file not found: {resolved_config_path}")

    config_data = load_config_data(resolved_config_path)
    defaults = config_data.get("usearch_otu_defaults", {})
    minsize = validate_positive_int(
        "minsize",
        defaults.get("minsize", FALLBACK_USEARCH_OTU_DEFAULTS["minsize"]),
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
        return load_usearch_otu_defaults(config_path)["minsize"]
    return validate_positive_int("minsize", minsize)


def run_usearch_otu_clustering(
    input_fasta: str,
    output_dir: str,
    threads: int = 1,
    minsize: Optional[int] = None,
    config_path: Optional[str] = None,
    usearch_path: Optional[str] = None,
    otu_fasta_path: Optional[str] = None,
    command_timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Run USEARCH 97% OTU clustering with cluster_otus."""

    resolved_input_fasta = ensure_input_fasta(input_fasta)
    resolved_output_dir = os.path.abspath(output_dir)
    os.makedirs(resolved_output_dir, exist_ok=True)

    resolved_threads = validate_threads(threads)
    resolved_minsize = _resolve_minsize(minsize, config_path)
    resolved_usearch = resolve_usearch_executable(usearch_path)

    otus_path = os.path.join(resolved_output_dir, "01_otus.fasta")
    otu_table_path = os.path.join(resolved_output_dir, "02_otu_table.tsv")

    print("[USEARCH OTU] Starting 97% OTU clustering workflow.")
    print(f"[USEARCH OTU] Input FASTA: {resolved_input_fasta}")
    print(f"[USEARCH OTU] Output directory: {resolved_output_dir}")
    print(f"[USEARCH OTU] Minimum abundance threshold: {resolved_minsize}")
    print(f"[USEARCH OTU] Threads: {resolved_threads}")
    print(f"[USEARCH OTU] USEARCH executable: {resolved_usearch}")

    print("[USEARCH OTU] Step 1/2: Clustering OTUs with cluster_otus.")
    run_command(
        [
            resolved_usearch,
            "-cluster_otus",
            resolved_input_fasta,
            "-minsize",
            str(resolved_minsize),
            "-otus",
            otus_path,
            "-relabel",
            "OTU_",
        ],
        timeout=command_timeout,
    )
    print(f"[USEARCH OTU] Step 1/2 complete: {otus_path}")

    print("[USEARCH OTU] Step 2/2: Building OTU abundance table with otutab.")
    run_command(
        [
            resolved_usearch,
            "-otutab",
            resolved_input_fasta,
            "-otus",
            otus_path,
            "-otutabout",
            otu_table_path,
            "-threads",
            str(resolved_threads),
        ],
        timeout=command_timeout,
    )
    print(f"[USEARCH OTU] Step 2/2 complete: {otu_table_path}")

    final_otu_fasta_path = otus_path
    if otu_fasta_path:
        final_otu_fasta_path = os.path.abspath(otu_fasta_path)
        parent_dir = os.path.dirname(final_otu_fasta_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        shutil.copyfile(otus_path, final_otu_fasta_path)
        print(f"[USEARCH OTU] Final OTU FASTA copied to: {final_otu_fasta_path}")

    print("[USEARCH OTU] Workflow finished successfully.")

    return {
        "minsize": resolved_minsize,
        "threads": resolved_threads,
        "command_timeout": command_timeout,
        "usearch": resolved_usearch,
        "otu_fasta": final_otu_fasta_path,
        "otu_table": otu_table_path,
    }
