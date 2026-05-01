"""OTU clustering workflow based on VSEARCH."""

from __future__ import annotations

import os
import shutil
from typing import Any, Dict, Optional

from src.utils.command_runner import run_command

from .workflow_common import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_VSEARCH_WINDOWS_PATH,
    ensure_input_fasta,
    filter_fasta_by_minsize,
    load_config_data,
    relabel_fasta,
    resolve_executable,
    validate_positive_int,
    validate_threads,
)

FALLBACK_VSEARCH_OTU_DEFAULTS = {"identity": 0.97, "minsize": 1}


def load_vsearch_otu_defaults(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load VSEARCH OTU defaults from config.yaml."""

    resolved_config_path = os.path.abspath(config_path or DEFAULT_CONFIG_PATH)
    default_config_path = os.path.abspath(DEFAULT_CONFIG_PATH)

    if not os.path.exists(resolved_config_path):
        if resolved_config_path == default_config_path:
            return dict(FALLBACK_VSEARCH_OTU_DEFAULTS)
        raise FileNotFoundError(f"Config file not found: {resolved_config_path}")

    config_data = load_config_data(resolved_config_path)
    defaults = config_data.get("vsearch_otu_defaults") or config_data.get(
        "otu_defaults", {}
    )

    raw_identity = defaults.get(
        "identity", FALLBACK_VSEARCH_OTU_DEFAULTS["identity"]
    )
    raw_minsize = defaults.get("minsize", FALLBACK_VSEARCH_OTU_DEFAULTS["minsize"])

    try:
        identity = float(raw_identity)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Invalid config value for vsearch_otu_defaults.identity; expected a number."
        ) from exc

    minsize = validate_positive_int("minsize", raw_minsize)
    return {"identity": identity, "minsize": minsize}


def resolve_vsearch_executable(vsearch_path: Optional[str] = None) -> str:
    """Resolve a usable VSEARCH executable path."""

    return resolve_executable(
        executable_name="vsearch",
        configured_path=vsearch_path,
        windows_default_path=DEFAULT_VSEARCH_WINDOWS_PATH,
        label="VSEARCH",
    )


def _resolve_identity(identity: Optional[float], config_path: Optional[str]) -> float:
    if identity is None:
        resolved_identity = load_vsearch_otu_defaults(config_path)["identity"]
    else:
        try:
            resolved_identity = float(identity)
        except (TypeError, ValueError) as exc:
            raise ValueError("identity must be a number between 0 and 1.") from exc

    if not 0 < resolved_identity <= 1:
        raise ValueError("identity must be a number between 0 and 1.")

    return resolved_identity


def _resolve_minsize(minsize: Optional[int], config_path: Optional[str]) -> int:
    if minsize is None:
        return load_vsearch_otu_defaults(config_path)["minsize"]
    return validate_positive_int("minsize", minsize)


def run_vsearch_otu_clustering(
    input_fasta: str,
    output_dir: str,
    threads: int = 1,
    identity: Optional[float] = None,
    minsize: Optional[int] = None,
    config_path: Optional[str] = None,
    vsearch_path: Optional[str] = None,
    otu_fasta_path: Optional[str] = None,
    command_timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Run a VSEARCH-based 97% OTU clustering workflow."""

    resolved_input_fasta = ensure_input_fasta(input_fasta)
    resolved_output_dir = os.path.abspath(output_dir)
    os.makedirs(resolved_output_dir, exist_ok=True)

    resolved_threads = validate_threads(threads)
    resolved_identity = _resolve_identity(identity, config_path)
    resolved_minsize = _resolve_minsize(minsize, config_path)
    resolved_vsearch = resolve_vsearch_executable(vsearch_path)
    identity_str = f"{resolved_identity:.4f}"

    filtered_input_path = os.path.join(resolved_output_dir, "00_filtered_input.fasta")
    centroids_path = os.path.join(resolved_output_dir, "01_centroids.fasta")
    nonchimeras_path = os.path.join(
        resolved_output_dir, "02_nonchimeric_centroids.fasta"
    )
    chimeras_path = os.path.join(resolved_output_dir, "02_chimeras.fasta")
    uchime_report_path = os.path.join(resolved_output_dir, "02_uchime_report.tsv")
    relabeled_otus_path = os.path.join(resolved_output_dir, "03_nonchimeric_otus.fasta")
    otu_table_path = os.path.join(resolved_output_dir, "04_otu_table.tsv")

    print("[VSEARCH OTU] Starting OTU clustering workflow.")
    print(f"[VSEARCH OTU] Input FASTA: {resolved_input_fasta}")
    print(f"[VSEARCH OTU] Output directory: {resolved_output_dir}")
    print(f"[VSEARCH OTU] Identity threshold: {resolved_identity}")
    print(f"[VSEARCH OTU] Minimum abundance threshold: {resolved_minsize}")
    print(f"[VSEARCH OTU] Threads: {resolved_threads}")
    print(f"[VSEARCH OTU] VSEARCH executable: {resolved_vsearch}")

    print("[VSEARCH OTU] Step 0/4: Filtering input sequences by abundance threshold.")
    filter_summary = filter_fasta_by_minsize(
        resolved_input_fasta,
        filtered_input_path,
        resolved_minsize,
    )
    if filter_summary["kept_records"] == 0:
        raise ValueError(
            "No sequences remain after minsize filtering. Lower the threshold and try again."
        )
    print(
        "[VSEARCH OTU] Step 0/4 complete: "
        f"{filter_summary['kept_records']} kept, "
        f"{filter_summary['skipped_records']} filtered out."
    )

    print("[VSEARCH OTU] Step 1/4: Clustering filtered sequences into OTU centroids.")
    run_command(
        [
            resolved_vsearch,
            "--cluster_size",
            filtered_input_path,
            "--id",
            identity_str,
            "--centroids",
            centroids_path,
            "--sizein",
            "--threads",
            str(resolved_threads),
        ],
        timeout=command_timeout,
    )
    print(f"[VSEARCH OTU] Step 1/4 complete: {centroids_path}")

    print("[VSEARCH OTU] Step 2/4: Removing chimeras with uchime_denovo.")
    run_command(
        [
            resolved_vsearch,
            "--uchime_denovo",
            centroids_path,
            "--nonchimeras",
            nonchimeras_path,
            "--chimeras",
            chimeras_path,
            "--uchimeout",
            uchime_report_path,
            "--threads",
            str(resolved_threads),
        ],
        timeout=command_timeout,
    )
    print(f"[VSEARCH OTU] Step 2/4 complete: {nonchimeras_path}")

    print("[VSEARCH OTU] Step 3/4: Relabeling non-chimeric centroids as OTUs.")
    otu_count = relabel_fasta(nonchimeras_path, relabeled_otus_path, prefix="OTU_")
    if otu_count == 0:
        raise ValueError("No non-chimeric OTUs were produced by uchime_denovo.")
    print(
        f"[VSEARCH OTU] Step 3/4 complete: {relabeled_otus_path} ({otu_count} OTUs)"
    )

    print("[VSEARCH OTU] Step 4/4: Mapping original sequences back to OTUs.")
    run_command(
        [
            resolved_vsearch,
            "--usearch_global",
            resolved_input_fasta,
            "--db",
            relabeled_otus_path,
            "--id",
            identity_str,
            "--strand",
            "plus",
            "--otutabout",
            otu_table_path,
            "--threads",
            str(resolved_threads),
        ],
        timeout=command_timeout,
    )
    print(f"[VSEARCH OTU] Step 4/4 complete: {otu_table_path}")

    final_otu_fasta_path = relabeled_otus_path
    if otu_fasta_path:
        final_otu_fasta_path = os.path.abspath(otu_fasta_path)
        parent_dir = os.path.dirname(final_otu_fasta_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        shutil.copyfile(relabeled_otus_path, final_otu_fasta_path)
        print(f"[VSEARCH OTU] Final OTU FASTA copied to: {final_otu_fasta_path}")

    print("[VSEARCH OTU] Workflow finished successfully.")

    return {
        "identity": resolved_identity,
        "minsize": resolved_minsize,
        "threads": resolved_threads,
        "command_timeout": command_timeout,
        "vsearch": resolved_vsearch,
        "filtered_input": filtered_input_path,
        "centroids": centroids_path,
        "nonchimeric_centroids": nonchimeras_path,
        "nonchimeric_otus": relabeled_otus_path,
        "chimeras": chimeras_path,
        "uchime_report": uchime_report_path,
        "otu_table": otu_table_path,
        "otu_fasta": final_otu_fasta_path,
    }


run_vsearch_clustering = run_vsearch_otu_clustering
