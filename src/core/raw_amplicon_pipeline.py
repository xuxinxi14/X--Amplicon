"""End-to-end raw FASTQ pipeline for X-Amplicon."""

from __future__ import annotations

import importlib
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import pandas as pd

from src.utils.provenance import (
    PROVENANCE_SCHEMA_VERSION,
    build_provenance_record,
    write_json_record,
    write_provenance_markdown,
)
from src.utils.command_runner import run_command

from .alpha_diversity import (
    calculate_alpha_diversity,
    calculate_richness_rarefaction_curve,
    rarefy_otutab,
)
from .beta_diversity import (
    DEFAULT_BETA_METRICS,
    PHYLOGENETIC_BETA_METRICS,
    calculate_beta_distance,
)
from .database_registry import resolve_database_record
from .otutab_filter import ROUTE_16S, ROUTE_ITS, ROUTE_NONE, run_otutab_filter
from .otu_table_generator import run_otutab_generation
from .phylogenetic_tree import run_phylogenetic_tree_generation
from .taxonomy_summary import parse_sintax_to_dataframe, summarize_taxa_abundance
from .usearch_ASV_unoise3 import run_usearch_unoise3_denoising
from .usearch_otu_cluster import run_usearch_otu_clustering
from .vsearch_otu_cluster import run_vsearch_otu_clustering
from .vsearch_sintax import run_vsearch_sintax
from .vsearch_uchime_ref import run_vsearch_uchime_ref
from .workflow_common import (
    DEFAULT_VSEARCH_WINDOWS_PATH,
    ensure_input_file,
    resolve_executable,
)

FEATURE_METHOD_ASV = "usearch-asv"
FEATURE_METHOD_USEARCH_OTU = "usearch-otu"
FEATURE_METHOD_VSEARCH_OTU = "vsearch-otu"
VALID_FEATURE_METHODS = {
    FEATURE_METHOD_ASV,
    FEATURE_METHOD_USEARCH_OTU,
    FEATURE_METHOD_VSEARCH_OTU,
}
MERGE_BACKEND_VSEARCH = "vsearch"
MERGE_BACKEND_PYTHON = "python"
VALID_MERGE_BACKENDS = {MERGE_BACKEND_VSEARCH, MERGE_BACKEND_PYTHON}
WORK_SUBDIRS = {
    "input": "00_input",
    "merged": "01_merged",
    "filtered": "02_filtered",
    "uniques": "03_uniques",
    "features": "04_features",
    "raw_results": "05_raw_results",
    "final": "06_final",
}
RUN_SUMMARY_FILENAME = "run_summary.json"
PROVENANCE_FILENAME = "provenance.json"
PROVENANCE_MD_FILENAME = "provenance.md"
DEFAULT_TAXONOMY_RANKS = (
    "Kingdom",
    "Phylum",
    "Class",
    "Order",
    "Family",
    "Genus",
    "Species",
)
_OPTIONAL_PATH_UNSET_TEXTS = {"none", "null"}
_BETA_TREE_SKIP_TEXTS = {
    "-",
    ".",
    "./",
    ".\\",
    ",",
    "empty",
    "omit",
    "omitted",
    "skip",
    "skipped",
    "unset",
    "__skip_unifrac__",
    "_skip_unifrac_",
}

def _ensure_input_directory(path: str, label: str) -> str:
    if not path:
        raise ValueError(f"{label} is required.")

    resolved_path = os.path.abspath(path)
    if not os.path.isdir(resolved_path):
        raise FileNotFoundError(f"{label} not found: {resolved_path}")

    return resolved_path


def _resolve_feature_method(feature_method: str) -> str:
    normalized = str(feature_method).strip().lower()
    if normalized not in VALID_FEATURE_METHODS:
        raise ValueError(
            "feature_method must be one of: usearch-asv, usearch-otu, vsearch-otu."
        )
    return normalized


def _resolve_filter_route(route: str) -> str:
    normalized = str(route).strip().lower()
    if normalized not in {ROUTE_16S, ROUTE_ITS, ROUTE_NONE}:
        raise ValueError("filter_route must be one of: 16s, its, none.")
    return normalized


def _resolve_merge_backend(merge_backend: str) -> str:
    normalized = str(merge_backend).strip().lower()
    if normalized not in VALID_MERGE_BACKENDS:
        raise ValueError("merge_backend must be one of: vsearch, python.")
    return normalized


def _read_sample_ids(metadata_path: str) -> list[str]:
    sample_ids: list[str] = []
    seen: set[str] = set()

    with open(metadata_path, "r", encoding="utf-8", newline=None) as handle:
        header_seen = False
        for raw_line in handle:
            line = raw_line.rstrip("\r\n")
            if not line:
                continue

            if not header_seen:
                header_seen = True
                continue

            sample_id = line.split("\t", 1)[0].strip()
            if not sample_id:
                raise ValueError("metadata contains an empty sample ID.")
            if sample_id in seen:
                raise ValueError(f"Duplicate sample ID in metadata: {sample_id}")
            seen.add(sample_id)
            sample_ids.append(sample_id)

    if not sample_ids:
        raise ValueError("metadata does not contain any sample rows.")

    return sample_ids


def _resolve_read_pairs(
    seq_dir: str,
    sample_ids: list[str],
    read1_suffix: str,
    read2_suffix: str,
) -> list[tuple[str, str, str]]:
    missing: list[str] = []
    pairs: list[tuple[str, str, str]] = []

    for sample_id in sample_ids:
        read1_path = os.path.join(seq_dir, f"{sample_id}{read1_suffix}")
        read2_path = os.path.join(seq_dir, f"{sample_id}{read2_suffix}")

        if not os.path.isfile(read1_path):
            missing.append(read1_path)
        if not os.path.isfile(read2_path):
            missing.append(read2_path)

        pairs.append((sample_id, read1_path, read2_path))

    if missing:
        rendered = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(
            "Required paired-end FASTQ files are missing:\n" + rendered
        )

    return pairs


def _prepare_work_dirs(output_root: str) -> Dict[str, str]:
    resolved_root = os.path.abspath(output_root)
    os.makedirs(resolved_root, exist_ok=True)

    resolved_dirs: Dict[str, str] = {"root": resolved_root}
    for key, name in WORK_SUBDIRS.items():
        path = os.path.join(resolved_root, name)
        os.makedirs(path, exist_ok=True)
        resolved_dirs[key] = path

    return resolved_dirs


def _normalize_summary_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalize_summary_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_normalize_summary_value(item) for item in value]

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    item_method = getattr(value, "item", None)
    if callable(item_method):
        return _normalize_summary_value(item_method())

    return str(value)


def _compact_dict(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


@dataclass
class PipelineContext:
    work_dirs: dict[str, str]
    summary_path: str
    provenance_path: str
    provenance_md_path: str
    summary: dict[str, Any]
    resolved: dict[str, Any] = field(default_factory=dict)
    results: dict[str, Any] = field(default_factory=dict)


def _duration_seconds(started_at: str | None, completed_at: str | None) -> float | None:
    if not started_at or not completed_at:
        return None
    try:
        started = datetime.fromisoformat(str(started_at))
        completed = datetime.fromisoformat(str(completed_at))
    except ValueError:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if completed.tzinfo is None:
        completed = completed.replace(tzinfo=timezone.utc)
    return round(max((completed - started).total_seconds(), 0.0), 6)


def _start_run_step(
    steps: list[dict[str, Any]],
    name: str,
    description: str,
) -> dict[str, Any]:
    step = {
        "name": name,
        "description": description,
        "status": "in_progress",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    steps.append(step)
    return step


def _complete_run_step(step: dict[str, Any], **details: Any) -> None:
    step["status"] = "completed"
    step["completed_at"] = datetime.now(timezone.utc).isoformat()
    step["duration_seconds"] = _duration_seconds(step.get("started_at"), step.get("completed_at"))
    if details:
        step["details"] = _normalize_summary_value(details)


def _fail_run_step(step: dict[str, Any], exc: Exception) -> None:
    step["status"] = "failed"
    step["completed_at"] = datetime.now(timezone.utc).isoformat()
    step["duration_seconds"] = _duration_seconds(step.get("started_at"), step.get("completed_at"))
    step["error"] = str(exc)


def _write_run_summary(summary_path: str, summary: dict[str, Any]) -> None:
    resolved_summary_path = os.path.abspath(summary_path)
    os.makedirs(os.path.dirname(resolved_summary_path), exist_ok=True)
    payload = _normalize_summary_value(summary)
    with open(resolved_summary_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _safe_write_run_summary(summary_path: str, summary: dict[str, Any]) -> None:
    try:
        _write_run_summary(summary_path, summary)
    except OSError as exc:
        print(
            "[RAW PIPELINE] Failed to write run summary: "
            f"{os.path.abspath(summary_path)} ({exc})"
        )


def _write_final_run_records(context: PipelineContext) -> None:
    context.summary["provenance_path"] = context.provenance_path
    context.summary["provenance_md_path"] = context.provenance_md_path
    context.summary["outputs"] = _build_pipeline_summary_outputs(context)
    _safe_write_run_summary(context.summary_path, context.summary)

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    provenance = build_provenance_record(
        project_root=project_root,
        summary=context.summary,
        provenance_path=context.provenance_path,
        provenance_md_path=context.provenance_md_path,
    )
    provenance_path = write_json_record(provenance, context.provenance_path)
    provenance_md_path = write_provenance_markdown(provenance, context.provenance_md_path)
    context.results["provenance"] = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "generated_at": provenance["generated_at"],
        "json": provenance_path,
        "markdown": provenance_md_path,
    }
    context.summary["provenance"] = context.results["provenance"]
    context.summary["outputs"] = _build_pipeline_summary_outputs(context)
    _safe_write_run_summary(context.summary_path, context.summary)


def _safe_write_final_run_records(context: PipelineContext) -> None:
    try:
        _write_final_run_records(context)
    except Exception as exc:
        context.summary["provenance_error"] = str(exc)
        context.summary["outputs"] = _build_pipeline_summary_outputs(context)
        _safe_write_run_summary(context.summary_path, context.summary)
        print(f"[RAW PIPELINE] Failed to write provenance record: {exc}")


def _normalize_optional_path(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    text = str(value).strip()
    if not text or text.lower() in _OPTIONAL_PATH_UNSET_TEXTS:
        return None

    return text


def _normalize_optional_tree_path(value: Optional[str]) -> Optional[str]:
    text = _normalize_optional_path(value)
    if text is None:
        return None

    unquoted_text = text.strip("\"'`").strip()
    lowered = unquoted_text.lower()
    basename = os.path.basename(unquoted_text).lower()
    if lowered in _BETA_TREE_SKIP_TEXTS or basename in _BETA_TREE_SKIP_TEXTS:
        return None
    if os.path.isdir(unquoted_text):
        return None
    return unquoted_text


def _resolve_database_summary_path(value: str) -> str:
    try:
        record = resolve_database_record(
            value,
            require_exists=False,
            include_hash=False,
        )
    except (KeyError, ValueError):
        return os.path.abspath(str(value))
    return os.path.abspath(str(record.get("path") or value))


def _build_effective_params(
    *,
    metadata_path: str,
    seq_dir: str,
    output_root: str,
    fastq_stripleft: int,
    fastq_stripright: int,
    fastq_maxee_rate: float,
    feature_minsize: int,
    feature_method: str,
    feature_identity: float,
    chimera_mode: str,
    reference_db: str,
    otutab_method: str,
    otutab_identity: float,
    annotation_database: str,
    sintax_cutoff: float,
    filter_route: str,
    threads: int,
    read1_suffix: str,
    read2_suffix: str,
    merge_backend: str,
    usearch_path: Optional[str],
    vsearch_path: Optional[str],
    beta_tree_path: Optional[str],
    rarefaction_depth: int,
    rarefaction_seed: int,
    command_timeout: Optional[float],
    params_source: Optional[str],
) -> dict[str, Any]:
    normalized_usearch_path = _normalize_optional_path(usearch_path)
    normalized_vsearch_path = _normalize_optional_path(vsearch_path)
    normalized_beta_tree_path = _normalize_optional_tree_path(beta_tree_path)
    normalized_params_source = _normalize_optional_path(params_source)
    resolved_merge_backend = _resolve_merge_backend(merge_backend)

    return {
        "metadata_path": os.path.abspath(metadata_path),
        "seq_dir": os.path.abspath(seq_dir),
        "output_root": os.path.abspath(output_root),
        "fastq_stripleft": fastq_stripleft,
        "fastq_stripright": fastq_stripright,
        "fastq_maxee_rate": fastq_maxee_rate,
        "feature_minsize": feature_minsize,
        "feature_method": feature_method,
        "feature_identity": feature_identity,
        "chimera_mode": chimera_mode,
        "reference_db": _resolve_database_summary_path(reference_db),
        "otutab_method": otutab_method,
        "otutab_identity": otutab_identity,
        "annotation_database": annotation_database,
        "sintax_cutoff": sintax_cutoff,
        "filter_route": filter_route,
        "threads": threads,
        "read1_suffix": read1_suffix,
        "read2_suffix": read2_suffix,
        "merge_backend": resolved_merge_backend,
        "usearch_path": (
            None
            if normalized_usearch_path is None
            else os.path.abspath(normalized_usearch_path)
        ),
        "vsearch_path": (
            None
            if normalized_vsearch_path is None
            else os.path.abspath(normalized_vsearch_path)
        ),
        "beta_tree_path": (
            None
            if normalized_beta_tree_path is None
            else os.path.abspath(normalized_beta_tree_path)
        ),
        "rarefaction_depth": rarefaction_depth,
        "rarefaction_seed": rarefaction_seed,
        "command_timeout": command_timeout,
        "params_source": (
            None
            if normalized_params_source is None
            else os.path.abspath(normalized_params_source)
        ),
    }


def _read_table(path: str) -> pd.DataFrame:
    table = pd.read_csv(path, sep="\t", header=0, index_col=0)
    if table.empty:
        raise ValueError(f"Table is empty: {path}")

    table.index = table.index.map(str)
    table.columns = table.columns.map(str)
    return table


def _write_table(
    table: pd.DataFrame,
    path: str,
    include_index: bool = True,
) -> str:
    resolved_path = os.path.abspath(path)
    parent_dir = os.path.dirname(resolved_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    table.to_csv(resolved_path, sep="\t", index=include_index)
    return resolved_path


def _load_tree(tree_path: str):
    from skbio import TreeNode

    with open(tree_path, "r", encoding="utf-8", newline=None) as handle:
        return TreeNode.read(handle)


def _generate_analysis_outputs(
    otutab_path: str,
    sintax_path: str,
    output_dir: str,
    beta_tree_path: Optional[str] = None,
    rarefaction_depth: int = 0,
    rarefaction_seed: int = 1,
) -> Dict[str, Any]:
    otutab = _read_table(otutab_path)
    taxonomy = parse_sintax_to_dataframe(sintax_path)

    resolved_output_dir = os.path.abspath(output_dir)
    alpha_dir = os.path.join(resolved_output_dir, "alpha")
    beta_dir = os.path.join(resolved_output_dir, "beta")
    taxonomy_summary_dir = os.path.join(resolved_output_dir, "taxonomy_summary")

    taxonomy_table_path = _write_table(
        taxonomy,
        os.path.join(resolved_output_dir, "taxonomy.tsv"),
        include_index=False,
    )
    rarefied_otutab, resolved_rarefaction_depth, discarded_samples = rarefy_otutab(
        otutab,
        depth=rarefaction_depth,
        seed=rarefaction_seed,
    )
    rarefied_otutab_path = _write_table(
        rarefied_otutab,
        os.path.join(resolved_output_dir, "otutab_rare.txt"),
    )
    alpha_diversity_path = _write_table(
        calculate_alpha_diversity(rarefied_otutab),
        os.path.join(alpha_dir, "alpha_diversity.tsv"),
    )
    alpha_rarefaction_path = _write_table(
        calculate_richness_rarefaction_curve(
            rarefied_otutab,
            seed=rarefaction_seed,
        ),
        os.path.join(alpha_dir, "alpha_rarefaction.tsv"),
    )

    beta_paths: Dict[str, str] = {}
    for metric in DEFAULT_BETA_METRICS:
        beta_paths[metric] = _write_table(
            calculate_beta_distance(otutab, metric),
            os.path.join(beta_dir, f"{metric}.tsv"),
        )

    generated_phylogenetic_beta_metrics: list[str] = []
    if beta_tree_path is not None:
        tree = _load_tree(beta_tree_path)
        for metric in PHYLOGENETIC_BETA_METRICS:
            beta_paths[metric] = _write_table(
                calculate_beta_distance(otutab, metric, tree=tree),
                os.path.join(beta_dir, f"{metric}.tsv"),
            )
            generated_phylogenetic_beta_metrics.append(metric)

    taxonomy_summary_paths: Dict[str, str] = {}
    for rank in DEFAULT_TAXONOMY_RANKS:
        taxonomy_summary_paths[rank] = _write_table(
            summarize_taxa_abundance(otutab, taxonomy, rank),
            os.path.join(taxonomy_summary_dir, f"{rank.lower()}.tsv"),
        )

    return {
        "taxonomy_table": taxonomy_table_path,
        "rarefied_otutab": rarefied_otutab_path,
        "rarefaction_depth": resolved_rarefaction_depth,
        "rarefaction_seed": rarefaction_seed,
        "discarded_rarefaction_samples": discarded_samples,
        "alpha_diversity": alpha_diversity_path,
        "alpha_rarefaction": alpha_rarefaction_path,
        "beta_dir": beta_dir,
        "beta_matrices": beta_paths,
        "generated_beta_metrics": list(beta_paths),
        "generated_phylogenetic_beta_metrics": generated_phylogenetic_beta_metrics,
        "skipped_beta_metrics": (
            []
            if beta_tree_path is not None
            else list(PHYLOGENETIC_BETA_METRICS)
        ),
        "taxonomy_summary_dir": taxonomy_summary_dir,
        "taxonomy_summaries": taxonomy_summary_paths,
    }


def _copy_metadata(metadata_path: str, input_dir: str) -> str:
    copied_metadata_path = os.path.join(input_dir, os.path.basename(metadata_path))
    shutil.copyfile(metadata_path, copied_metadata_path)
    return copied_metadata_path


def _load_vendor_fastq_mergepairs() -> Any:
    try:
        module = importlib.import_module("src.vendor.fastq_mergepairs")
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc
    return module.fastq_mergepairs


def _load_vendor_fastx_filter_run() -> Any:
    try:
        module = importlib.import_module("src.vendor.fastx_filter")
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc
    return module.run


def _load_vendor_derep_run() -> Any:
    try:
        module = importlib.import_module("src.vendor.derep_fulllength")
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc
    return module.run


def _concatenate_files(input_paths: list[str], output_path: str) -> None:
    with open(output_path, "wb") as destination:
        for input_path in input_paths:
            with open(input_path, "rb") as source:
                shutil.copyfileobj(source, destination)


def _prefix_fastq_headers(path: str, sample_id: str) -> None:
    resolved_path = os.path.abspath(path)
    normalized_sample_id = str(sample_id).strip()
    if not normalized_sample_id:
        raise ValueError("sample_id is required to relabel merged FASTQ headers.")

    temp_path = resolved_path + ".tmp"
    line_count = 0

    try:
        with open(resolved_path, "r", encoding="utf-8", newline=None) as source, open(
            temp_path, "w", encoding="utf-8", newline="\n"
        ) as destination:
            for raw_line in source:
                line_count += 1
                line = raw_line.rstrip("\r\n")
                record_offset = (line_count - 1) % 4

                if record_offset == 0:
                    if not line.startswith("@"):
                        raise ValueError(
                            "Merged FASTQ header line must start with '@': "
                            f"{resolved_path} line {line_count}"
                        )
                    destination.write(f"@{normalized_sample_id}.{line[1:]}\n")
                elif record_offset == 2:
                    if not line.startswith("+"):
                        raise ValueError(
                            "Merged FASTQ separator line must start with '+': "
                            f"{resolved_path} line {line_count}"
                        )
                    destination.write(line + "\n")
                else:
                    destination.write(line + "\n")

        if line_count == 0:
            raise ValueError(f"Merged FASTQ is empty: {resolved_path}")
        if line_count % 4 != 0:
            raise ValueError(
                "Merged FASTQ does not contain complete 4-line records: "
                f"{resolved_path}"
            )

        os.replace(temp_path, resolved_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def _run_vsearch_mergepairs(
    *,
    read1_path: str,
    read2_path: str,
    output_path: str,
    vsearch_path: Optional[str],
    threads: int,
    command_timeout: Optional[float],
) -> dict[str, Any]:
    resolved_vsearch = resolve_executable(
        "vsearch",
        configured_path=vsearch_path,
        windows_default_path=DEFAULT_VSEARCH_WINDOWS_PATH,
        label="VSEARCH",
    )
    command = [
        resolved_vsearch,
        "--fastq_mergepairs",
        read1_path,
        "--reverse",
        read2_path,
        "--fastqout",
        output_path,
        "--threads",
        str(int(threads)),
        "--fastq_minovlen",
        "10",
        "--fastq_maxdiffs",
        "10",
        "--fastq_minmergelen",
        "0",
        "--fastq_maxmergelen",
        "1000000",
    ]
    result = run_command(command, timeout=command_timeout)
    return {
        "backend": MERGE_BACKEND_VSEARCH,
        "read1_path": read1_path,
        "read2_path": read2_path,
        "output_path": output_path,
        "command": list(result.command),
        "returncode": result.returncode,
    }


def _execute_pipeline_step(
    context: PipelineContext,
    name: str,
    description: str,
    action: Callable[[], dict[str, Any] | None],
) -> None:
    step = _start_run_step(context.summary["steps"], name, description)
    context.summary["current_step"] = name
    context.summary["current_step_description"] = description
    context.summary["outputs"] = _build_pipeline_summary_outputs(context)
    _safe_write_run_summary(context.summary_path, context.summary)
    try:
        details = action() or {}
    except Exception as exc:
        _fail_run_step(step, exc)
        context.summary["failed_step"] = name
        context.summary["outputs"] = _build_pipeline_summary_outputs(context)
        _safe_write_run_summary(context.summary_path, context.summary)
        raise

    _complete_run_step(step, **details)
    context.summary["current_step"] = None
    context.summary["current_step_description"] = None
    context.summary["outputs"] = _build_pipeline_summary_outputs(context)
    _safe_write_run_summary(context.summary_path, context.summary)


def _build_pipeline_summary_outputs(context: PipelineContext) -> dict[str, Any]:
    return _compact_dict(
        {
            "metadata": context.results.get("metadata"),
            "all_fastq": context.results.get("all_fastq"),
            "filtered_fasta": context.results.get("filtered_fasta"),
            "uniques_fasta": context.results.get("uniques_fasta"),
            "raw_otus_fasta": context.results.get("raw_otus_fasta"),
            "raw_otutab": context.results.get("raw_otutab"),
            "raw_sintax": context.results.get("raw_sintax"),
            "feature_outputs": context.results.get("feature_outputs"),
            "chimera_outputs": context.results.get("chimera_outputs"),
            "otutab_outputs": context.results.get("otutab_outputs"),
            "sintax_outputs": context.results.get("sintax_outputs"),
            "final_outputs": context.results.get("final_outputs"),
            "phylogenetic_tree": context.results.get("phylogenetic_tree"),
            "analysis_outputs": context.results.get("analysis_outputs"),
            "provenance": context.results.get("provenance"),
        }
    )


def _build_pipeline_outputs(context: PipelineContext) -> dict[str, Any]:
    return {
        "metadata": context.results["metadata"],
        "sample_ids": context.results["sample_ids"],
        "merge_summaries": context.results["merge_summaries"],
        "all_fastq": context.results["all_fastq"],
        "filtered_fasta": context.results["filtered_fasta"],
        "uniques_fasta": context.results["uniques_fasta"],
        "feature_outputs": context.results["feature_outputs"],
        "chimera_outputs": context.results["chimera_outputs"],
        "raw_otus_fasta": context.results["raw_otus_fasta"],
        "raw_otutab": context.results["raw_otutab"],
        "raw_sintax": context.results["raw_sintax"],
        "otutab_outputs": context.results["otutab_outputs"],
        "sintax_outputs": context.results["sintax_outputs"],
        "final_outputs": context.results["final_outputs"],
        "phylogenetic_tree": context.results["phylogenetic_tree"],
        "analysis_outputs": context.results["analysis_outputs"],
        "work_dirs": context.work_dirs,
        "summary_path": context.summary_path,
        "provenance": context.results.get("provenance"),
    }


def _cleanup_temporary_files(work_root: str) -> dict[str, Any]:
    cleaned_paths: list[str] = []
    cleanup_errors: list[dict[str, str]] = []

    for current_root, _, filenames in os.walk(os.path.abspath(work_root)):
        for filename in filenames:
            if not filename.endswith(".tmp"):
                continue

            target_path = os.path.join(current_root, filename)
            try:
                os.remove(target_path)
                cleaned_paths.append(target_path)
            except OSError as exc:
                cleanup_errors.append({"path": target_path, "error": str(exc)})

    return {
        "temporary_pattern": "*.tmp",
        "cleaned_paths": cleaned_paths,
        "errors": cleanup_errors,
    }


def _step_validate_inputs(
    context: PipelineContext,
    *,
    metadata_path: str,
    seq_dir: str,
    fastq_stripleft: int,
    fastq_stripright: int,
    fastq_maxee_rate: float,
    feature_minsize: int,
    feature_method: str,
    feature_identity: float,
    chimera_mode: str,
    reference_db: str,
    otutab_method: str,
    otutab_identity: float,
    annotation_database: str,
    sintax_cutoff: float,
    filter_route: str,
    threads: int,
    read1_suffix: str,
    read2_suffix: str,
    merge_backend: str,
    usearch_path: Optional[str],
    vsearch_path: Optional[str],
    beta_tree_path: Optional[str],
    rarefaction_depth: int,
    rarefaction_seed: int,
    command_timeout: Optional[float],
    params_source: Optional[str],
) -> dict[str, Any]:
    resolved_metadata_path = ensure_input_file(metadata_path, "metadata_path")
    resolved_seq_dir = _ensure_input_directory(seq_dir, "seq_dir")
    normalized_beta_tree_path = _normalize_optional_tree_path(beta_tree_path)
    resolved_beta_tree_path = (
        None
        if normalized_beta_tree_path is None
        else ensure_input_file(normalized_beta_tree_path, "beta_tree_path")
    )
    resolved_feature_method = _resolve_feature_method(feature_method)
    resolved_filter_route = _resolve_filter_route(filter_route)
    resolved_merge_backend = _resolve_merge_backend(merge_backend)
    sample_ids = _read_sample_ids(resolved_metadata_path)
    read_pairs = _resolve_read_pairs(
        resolved_seq_dir,
        sample_ids,
        read1_suffix,
        read2_suffix,
    )
    copied_metadata_path = _copy_metadata(resolved_metadata_path, context.work_dirs["input"])

    context.resolved.update(
        {
            "metadata_path": resolved_metadata_path,
            "seq_dir": resolved_seq_dir,
            "beta_tree_path": resolved_beta_tree_path,
            "feature_method": resolved_feature_method,
            "filter_route": resolved_filter_route,
            "merge_backend": resolved_merge_backend,
            "rarefaction_depth": int(rarefaction_depth),
            "rarefaction_seed": int(rarefaction_seed),
        }
    )
    context.results.update(
        {
            "metadata": copied_metadata_path,
            "sample_ids": sample_ids,
            "read_pairs": read_pairs,
        }
    )
    context.summary["sample_ids"] = sample_ids
    context.summary["effective_params"] = _build_effective_params(
        metadata_path=resolved_metadata_path,
        seq_dir=resolved_seq_dir,
        output_root=context.work_dirs["root"],
        fastq_stripleft=fastq_stripleft,
        fastq_stripright=fastq_stripright,
        fastq_maxee_rate=fastq_maxee_rate,
        feature_minsize=feature_minsize,
        feature_method=resolved_feature_method,
        feature_identity=feature_identity,
        chimera_mode=chimera_mode,
        reference_db=reference_db,
        otutab_method=otutab_method,
        otutab_identity=otutab_identity,
        annotation_database=annotation_database,
        sintax_cutoff=sintax_cutoff,
        filter_route=resolved_filter_route,
        threads=threads,
        read1_suffix=read1_suffix,
        read2_suffix=read2_suffix,
        merge_backend=resolved_merge_backend,
        usearch_path=usearch_path,
        vsearch_path=vsearch_path,
        beta_tree_path=resolved_beta_tree_path,
        rarefaction_depth=rarefaction_depth,
        rarefaction_seed=rarefaction_seed,
        command_timeout=command_timeout,
        params_source=params_source,
    )

    print("[RAW PIPELINE] Starting X-Amplicon raw FASTQ pipeline.")
    print(f"[RAW PIPELINE] Metadata: {resolved_metadata_path}")
    print(f"[RAW PIPELINE] Sequence directory: {resolved_seq_dir}")
    print(f"[RAW PIPELINE] Output root: {context.work_dirs['root']}")
    print(f"[RAW PIPELINE] Feature method: {resolved_feature_method}")
    print(f"[RAW PIPELINE] Merge backend: {resolved_merge_backend}")
    print(f"[RAW PIPELINE] OTU table method: {otutab_method}")
    print(f"[RAW PIPELINE] Annotation database: {annotation_database}")
    print(f"[RAW PIPELINE] Filter route: {resolved_filter_route}")
    print(f"[RAW PIPELINE] Sample count: {len(sample_ids)}")
    if command_timeout is not None:
        print(f"[RAW PIPELINE] External command timeout: {command_timeout} seconds")

    return {
        "metadata_path": resolved_metadata_path,
        "seq_dir": resolved_seq_dir,
        "sample_count": len(sample_ids),
        "matched_read_pairs": len(read_pairs),
        "beta_tree_path": resolved_beta_tree_path,
        "merge_backend": resolved_merge_backend,
        "rarefaction_depth": int(rarefaction_depth),
        "rarefaction_seed": int(rarefaction_seed),
    }


def _step_merge_pairs(context: PipelineContext) -> dict[str, Any]:
    merge_backend = _resolve_merge_backend(
        str(context.resolved.get("merge_backend", MERGE_BACKEND_VSEARCH))
    )
    mergepairs = (
        _load_vendor_fastq_mergepairs()
        if merge_backend == MERGE_BACKEND_PYTHON
        else None
    )
    effective_params = context.summary.get("effective_params", {})
    assert isinstance(effective_params, dict)
    merged_fastq_paths: list[str] = []
    merge_summaries: list[Dict[str, Any]] = []

    for sample_id, read1_path, read2_path in context.results["read_pairs"]:
        merged_fastq_path = os.path.join(
            context.work_dirs["merged"],
            f"{sample_id}.merged.fq",
        )
        if merge_backend == MERGE_BACKEND_PYTHON:
            assert mergepairs is not None
            merge_summary = mergepairs(
                read1_path=read1_path,
                read2_path=read2_path,
                output_path=merged_fastq_path,
            )
            merge_summary = {"backend": MERGE_BACKEND_PYTHON, **merge_summary}
        else:
            merge_summary = _run_vsearch_mergepairs(
                read1_path=read1_path,
                read2_path=read2_path,
                output_path=merged_fastq_path,
                vsearch_path=(
                    None
                    if effective_params.get("vsearch_path") is None
                    else str(effective_params["vsearch_path"])
                ),
                threads=int(effective_params.get("threads", 1)),
                command_timeout=(
                    None
                    if effective_params.get("command_timeout") is None
                    else float(effective_params["command_timeout"])
                ),
            )
        _prefix_fastq_headers(merged_fastq_path, sample_id)
        merge_summaries.append({"sample_id": sample_id, **merge_summary})
        merged_fastq_paths.append(merged_fastq_path)

    all_fastq_path = os.path.join(context.work_dirs["merged"], "all.fq")
    _concatenate_files(merged_fastq_paths, all_fastq_path)

    context.results["merge_summaries"] = merge_summaries
    context.results["all_fastq"] = all_fastq_path

    return {
        "merged_fastq_files": merged_fastq_paths,
        "merged_fastq_bundle": all_fastq_path,
        "sample_count": len(merged_fastq_paths),
        "backend": merge_backend,
    }


def _step_filter_reads(
    context: PipelineContext,
    *,
    fastq_stripleft: int,
    fastq_stripright: int,
    fastq_maxee_rate: float,
) -> dict[str, Any]:
    fastx_filter_run = _load_vendor_fastx_filter_run()
    filtered_fasta_path = os.path.join(context.work_dirs["filtered"], "filtered.fa")
    filter_result = fastx_filter_run(
        {
            "fastx_filter": context.results["all_fastq"],
            "fastaout": filtered_fasta_path,
            "fastq_stripleft": fastq_stripleft,
            "fastq_stripright": fastq_stripright,
            "fastq_maxee_rate": fastq_maxee_rate,
            "fastq_maxns": -1,
            "minlen": 1,
        }
    )
    if not filter_result.success:
        if filter_result.error is None:
            raise ValueError("fastx_filter failed without a structured error message.")
        raise ValueError(filter_result.error.message)

    context.results["filtered_fasta"] = filtered_fasta_path
    return {"filtered_fasta": filtered_fasta_path}


def _step_dereplicate_sequences(
    context: PipelineContext,
    *,
    feature_minsize: int,
) -> dict[str, Any]:
    derep_run = _load_vendor_derep_run()
    uniques_fasta_path = os.path.join(context.work_dirs["uniques"], "uniques.fa")
    derep_result = derep_run(
        {
            "derep_fulllength": context.results["filtered_fasta"],
            "output": uniques_fasta_path,
            "sizeout": True,
            "minuniquesize": feature_minsize,
            "relabel": "Uni_",
            "fasta_width": 80,
        }
    )
    if not derep_result.success:
        raise ValueError(derep_result.error or "derep_fulllength failed.")

    context.results["uniques_fasta"] = uniques_fasta_path
    return {"uniques_fasta": uniques_fasta_path}


def _run_feature_generation(
    feature_method: str,
    uniques_fasta: str,
    features_dir: str,
    feature_minsize: int,
    threads: int,
    usearch_path: Optional[str],
    vsearch_path: Optional[str],
    feature_identity: float,
    command_timeout: Optional[float],
) -> Dict[str, Any]:
    final_feature_fasta = os.path.join(features_dir, "otus.fa")

    if feature_method == FEATURE_METHOD_ASV:
        return run_usearch_unoise3_denoising(
            input_fasta=uniques_fasta,
            output_dir=os.path.join(features_dir, "usearch_asv"),
            threads=threads,
            minsize=feature_minsize,
            usearch_path=usearch_path,
            asv_fasta_path=final_feature_fasta,
            command_timeout=command_timeout,
        )

    if feature_method == FEATURE_METHOD_USEARCH_OTU:
        return run_usearch_otu_clustering(
            input_fasta=uniques_fasta,
            output_dir=os.path.join(features_dir, "usearch_otu"),
            threads=threads,
            minsize=feature_minsize,
            usearch_path=usearch_path,
            otu_fasta_path=final_feature_fasta,
            command_timeout=command_timeout,
        )

    return run_vsearch_otu_clustering(
        input_fasta=uniques_fasta,
        output_dir=os.path.join(features_dir, "vsearch_otu"),
        threads=threads,
        identity=feature_identity,
        minsize=feature_minsize,
        vsearch_path=vsearch_path,
        otu_fasta_path=final_feature_fasta,
        command_timeout=command_timeout,
    )


def _step_generate_features(
    context: PipelineContext,
    *,
    feature_minsize: int,
    threads: int,
    usearch_path: Optional[str],
    vsearch_path: Optional[str],
    feature_identity: float,
    command_timeout: Optional[float],
) -> dict[str, Any]:
    feature_outputs = _run_feature_generation(
        context.resolved["feature_method"],
        context.results["uniques_fasta"],
        context.work_dirs["features"],
        feature_minsize,
        threads,
        usearch_path,
        vsearch_path,
        feature_identity,
        command_timeout,
    )
    context.results["feature_outputs"] = feature_outputs
    return {
        "feature_method": context.resolved["feature_method"],
        "outputs": feature_outputs,
    }


def _step_remove_chimeras(
    context: PipelineContext,
    *,
    threads: int,
    reference_db: str,
    chimera_mode: str,
    vsearch_path: Optional[str],
    command_timeout: Optional[float],
) -> dict[str, Any]:
    raw_otus_fasta_path = os.path.join(context.work_dirs["raw_results"], "otus.fa")
    chimera_outputs = run_vsearch_uchime_ref(
        input_fasta=os.path.join(context.work_dirs["features"], "otus.fa"),
        output_dir=os.path.join(context.work_dirs["raw_results"], "uchime_ref"),
        threads=threads,
        reference_db=reference_db,
        chimera_mode=chimera_mode,
        vsearch_path=vsearch_path,
        output_fasta_path=raw_otus_fasta_path,
        command_timeout=command_timeout,
    )
    context.results["raw_otus_fasta"] = raw_otus_fasta_path
    context.results["chimera_outputs"] = chimera_outputs
    context.summary["effective_params"]["reference_db"] = chimera_outputs["reference_db"]
    return {"outputs": chimera_outputs}


def _step_build_raw_feature_table(
    context: PipelineContext,
    *,
    otutab_method: str,
    threads: int,
    otutab_identity: float,
    usearch_path: Optional[str],
    vsearch_path: Optional[str],
    command_timeout: Optional[float],
) -> dict[str, Any]:
    raw_otutab_path = os.path.join(context.work_dirs["raw_results"], "otutab.txt")
    otutab_outputs = run_otutab_generation(
        input_fasta=context.results["filtered_fasta"],
        representative_fasta=context.results["raw_otus_fasta"],
        output_dir=context.work_dirs["raw_results"],
        method=otutab_method,
        threads=threads,
        identity=otutab_identity,
        tool_path=usearch_path if otutab_method == "usearch" else vsearch_path,
        output_table_path=raw_otutab_path,
        command_timeout=command_timeout,
    )
    context.results["raw_otutab"] = raw_otutab_path
    context.results["otutab_outputs"] = otutab_outputs
    return {"outputs": otutab_outputs}


def _step_annotate_taxonomy(
    context: PipelineContext,
    *,
    threads: int,
    annotation_database: str,
    sintax_cutoff: float,
    vsearch_path: Optional[str],
    command_timeout: Optional[float],
) -> dict[str, Any]:
    raw_sintax_path = os.path.join(context.work_dirs["raw_results"], "otus.sintax")
    sintax_outputs = run_vsearch_sintax(
        input_fasta=context.results["raw_otus_fasta"],
        output_dir=context.work_dirs["raw_results"],
        threads=threads,
        database=annotation_database,
        sintax_cutoff=sintax_cutoff,
        vsearch_path=vsearch_path,
        output_annotation_path=raw_sintax_path,
        command_timeout=command_timeout,
    )
    context.results["raw_sintax"] = raw_sintax_path
    context.results["sintax_outputs"] = sintax_outputs
    context.summary["effective_params"]["annotation_database"] = sintax_outputs.get(
        "database",
        annotation_database,
    )
    if sintax_outputs.get("database_path") is not None:
        context.summary["effective_params"]["annotation_database_path"] = sintax_outputs[
            "database_path"
        ]
    return {"outputs": sintax_outputs}


def _step_filter_final_outputs(
    context: PipelineContext,
    *,
    usearch_path: Optional[str],
    command_timeout: Optional[float],
) -> dict[str, Any]:
    resolved_filter_route = context.resolved["filter_route"]
    if resolved_filter_route == ROUTE_16S:
        stat_path = os.path.join(context.work_dirs["raw_results"], "otutab_nonBac.stat")
    elif resolved_filter_route == ROUTE_ITS:
        stat_path = os.path.join(context.work_dirs["raw_results"], "otutab_nonFungi.stat")
    else:
        stat_path = None

    final_outputs = run_otutab_filter(
        input_table=context.results["raw_otutab"],
        taxonomy_path=context.results["raw_sintax"],
        representative_fasta=context.results["raw_otus_fasta"],
        output_dir=context.work_dirs["final"],
        route=resolved_filter_route,
        usearch_path=usearch_path,
        output_table_path=os.path.join(context.work_dirs["final"], "otutab.txt"),
        output_fasta_path=os.path.join(context.work_dirs["final"], "otus.fa"),
        output_taxonomy_path=os.path.join(context.work_dirs["final"], "otus.sintax"),
        output_stat_path=stat_path,
        discard_path=os.path.join(context.work_dirs["raw_results"], "otus.sintax.discard"),
        output_id_path=os.path.join(context.work_dirs["final"], "otutab.id"),
        command_timeout=command_timeout,
    )
    context.results["final_outputs"] = final_outputs
    return {"outputs": final_outputs}


def _step_generate_phylogenetic_tree(context: PipelineContext) -> dict[str, Any]:
    if context.resolved.get("beta_tree_path") is not None:
        tree_path = context.resolved["beta_tree_path"]
        context.results["phylogenetic_tree"] = {
            "tree_path": tree_path,
            "source": "provided",
        }
        return {
            "tree_path": tree_path,
            "source": "provided",
        }

    tree_outputs = run_phylogenetic_tree_generation(
        input_fasta=context.results["final_outputs"]["representative_fasta"],
        output_tree_path=os.path.join(context.work_dirs["final"], "otus.tree"),
        linkage="max",
        distance_method="edit",
    )
    tree_outputs["source"] = "generated"
    context.resolved["beta_tree_path"] = tree_outputs["tree_path"]
    context.results["phylogenetic_tree"] = tree_outputs
    context.summary["effective_params"]["beta_tree_path"] = tree_outputs["tree_path"]
    return tree_outputs


def _step_generate_analysis_outputs(context: PipelineContext) -> dict[str, Any]:
    analysis_outputs = _generate_analysis_outputs(
        otutab_path=context.results["final_outputs"]["feature_table"],
        sintax_path=context.results["final_outputs"]["taxonomy"],
        output_dir=context.work_dirs["final"],
        beta_tree_path=context.resolved["beta_tree_path"],
        rarefaction_depth=context.resolved["rarefaction_depth"],
        rarefaction_seed=context.resolved["rarefaction_seed"],
    )
    context.results["analysis_outputs"] = analysis_outputs
    return {
        "taxonomy_table": analysis_outputs["taxonomy_table"],
        "rarefied_otutab": analysis_outputs["rarefied_otutab"],
        "rarefaction_depth": analysis_outputs["rarefaction_depth"],
        "alpha_diversity": analysis_outputs["alpha_diversity"],
        "alpha_rarefaction": analysis_outputs["alpha_rarefaction"],
        "beta_matrices": analysis_outputs["beta_matrices"],
        "generated_beta_metrics": analysis_outputs["generated_beta_metrics"],
        "skipped_beta_metrics": analysis_outputs["skipped_beta_metrics"],
        "taxonomy_summaries": analysis_outputs["taxonomy_summaries"],
    }


def run_raw_amplicon_pipeline(
    metadata_path: str,
    seq_dir: str,
    output_root: str,
    fastq_stripleft: int,
    fastq_stripright: int,
    fastq_maxee_rate: float,
    feature_minsize: int = 10,
    feature_method: str = FEATURE_METHOD_ASV,
    feature_identity: float = 0.97,
    chimera_mode: str = "ref",
    reference_db: str = "database/rdp_16s_v18.fa",
    otutab_method: str = "usearch",
    otutab_identity: float = 0.97,
    annotation_database: str = "rdp_16s_v18",
    sintax_cutoff: float = 0.1,
    filter_route: str = ROUTE_16S,
    threads: int = 1,
    read1_suffix: str = "_1.fq.gz",
    read2_suffix: str = "_2.fq.gz",
    merge_backend: str = MERGE_BACKEND_VSEARCH,
    usearch_path: Optional[str] = None,
    vsearch_path: Optional[str] = None,
    beta_tree_path: Optional[str] = None,
    rarefaction_depth: int = 0,
    rarefaction_seed: int = 1,
    command_timeout: Optional[float] = None,
    params_source: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the integrated raw FASTQ pipeline."""

    usearch_path = _normalize_optional_path(usearch_path)
    vsearch_path = _normalize_optional_path(vsearch_path)
    merge_backend = _resolve_merge_backend(merge_backend)
    beta_tree_path = _normalize_optional_tree_path(beta_tree_path)
    params_source = _normalize_optional_path(params_source)
    work_dirs = _prepare_work_dirs(output_root)
    summary_path = os.path.join(work_dirs["final"], RUN_SUMMARY_FILENAME)
    provenance_path = os.path.join(work_dirs["final"], PROVENANCE_FILENAME)
    provenance_md_path = os.path.join(work_dirs["final"], PROVENANCE_MD_FILENAME)
    context = PipelineContext(
        work_dirs=work_dirs,
        summary_path=summary_path,
        provenance_path=provenance_path,
        provenance_md_path=provenance_md_path,
        summary={
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "failed_step": None,
            "error": None,
            "summary_path": summary_path,
            "provenance_path": provenance_path,
            "provenance_md_path": provenance_md_path,
            "effective_params": _build_effective_params(
                metadata_path=metadata_path,
                seq_dir=seq_dir,
                output_root=output_root,
                fastq_stripleft=fastq_stripleft,
                fastq_stripright=fastq_stripright,
                fastq_maxee_rate=fastq_maxee_rate,
                feature_minsize=feature_minsize,
                feature_method=feature_method,
                feature_identity=feature_identity,
                chimera_mode=chimera_mode,
                reference_db=reference_db,
                otutab_method=otutab_method,
                otutab_identity=otutab_identity,
                annotation_database=annotation_database,
                sintax_cutoff=sintax_cutoff,
                filter_route=filter_route,
                threads=threads,
                read1_suffix=read1_suffix,
                read2_suffix=read2_suffix,
                merge_backend=merge_backend,
                usearch_path=usearch_path,
                vsearch_path=vsearch_path,
                beta_tree_path=beta_tree_path,
                rarefaction_depth=rarefaction_depth,
                rarefaction_seed=rarefaction_seed,
                command_timeout=command_timeout,
                params_source=params_source,
            ),
            "work_dirs": work_dirs,
            "steps": [],
            "outputs": {},
        },
    )

    try:
        _execute_pipeline_step(
            context,
            "validate_inputs",
            "Validate required inputs, parameters, and paired-end sample matches.",
            lambda: _step_validate_inputs(
                context,
                metadata_path=metadata_path,
                seq_dir=seq_dir,
                fastq_stripleft=fastq_stripleft,
                fastq_stripright=fastq_stripright,
                fastq_maxee_rate=fastq_maxee_rate,
                feature_minsize=feature_minsize,
                feature_method=feature_method,
                feature_identity=feature_identity,
                chimera_mode=chimera_mode,
                reference_db=reference_db,
                otutab_method=otutab_method,
                otutab_identity=otutab_identity,
                annotation_database=annotation_database,
                sintax_cutoff=sintax_cutoff,
                filter_route=filter_route,
                threads=threads,
                read1_suffix=read1_suffix,
                read2_suffix=read2_suffix,
                merge_backend=merge_backend,
                usearch_path=usearch_path,
                vsearch_path=vsearch_path,
                beta_tree_path=beta_tree_path,
                rarefaction_depth=rarefaction_depth,
                rarefaction_seed=rarefaction_seed,
                command_timeout=command_timeout,
                params_source=params_source,
            ),
        )
        _execute_pipeline_step(
            context,
            "merge_pairs",
            "Merge paired-end FASTQ files sample by sample.",
            lambda: _step_merge_pairs(context),
        )
        _execute_pipeline_step(
            context,
            "filter_reads",
            "Trim and quality-filter merged reads.",
            lambda: _step_filter_reads(
                context,
                fastq_stripleft=fastq_stripleft,
                fastq_stripright=fastq_stripright,
                fastq_maxee_rate=fastq_maxee_rate,
            ),
        )
        _execute_pipeline_step(
            context,
            "dereplicate_sequences",
            "Collapse identical reads into unique sequences.",
            lambda: _step_dereplicate_sequences(
                context,
                feature_minsize=feature_minsize,
            ),
        )
        _execute_pipeline_step(
            context,
            "generate_features",
            "Generate representative feature sequences as ASVs or OTUs.",
            lambda: _step_generate_features(
                context,
                feature_minsize=feature_minsize,
                threads=threads,
                usearch_path=usearch_path,
                vsearch_path=vsearch_path,
                feature_identity=feature_identity,
                command_timeout=command_timeout,
            ),
        )
        _execute_pipeline_step(
            context,
            "remove_chimeras",
            "Run reference-based chimera filtering before abundance table generation.",
            lambda: _step_remove_chimeras(
                context,
                threads=threads,
                reference_db=reference_db,
                chimera_mode=chimera_mode,
                vsearch_path=vsearch_path,
                command_timeout=command_timeout,
            ),
        )
        _execute_pipeline_step(
            context,
            "build_raw_feature_table",
            "Map reads back to representative sequences to build the raw OTU table.",
            lambda: _step_build_raw_feature_table(
                context,
                otutab_method=otutab_method,
                threads=threads,
                otutab_identity=otutab_identity,
                usearch_path=usearch_path,
                vsearch_path=vsearch_path,
                command_timeout=command_timeout,
            ),
        )
        _execute_pipeline_step(
            context,
            "annotate_taxonomy",
            "Annotate representative sequences with SINTAX taxonomy.",
            lambda: _step_annotate_taxonomy(
                context,
                threads=threads,
                annotation_database=annotation_database,
                sintax_cutoff=sintax_cutoff,
                vsearch_path=vsearch_path,
                command_timeout=command_timeout,
            ),
        )
        _execute_pipeline_step(
            context,
            "filter_final_outputs",
            "Filter taxonomy and export the final core result set.",
            lambda: _step_filter_final_outputs(
                context,
                usearch_path=usearch_path,
                command_timeout=command_timeout,
            ),
        )
        _execute_pipeline_step(
            context,
            "generate_phylogenetic_tree",
            "Generate or register the rooted OTU/ASV tree for UniFrac.",
            lambda: _step_generate_phylogenetic_tree(context),
        )
        _execute_pipeline_step(
            context,
            "generate_analysis_outputs",
            "Build taxonomy, alpha diversity, beta diversity, and taxonomy summaries.",
            lambda: _step_generate_analysis_outputs(context),
        )

        context.summary["status"] = "success"
        context.summary["completed_at"] = datetime.now(timezone.utc).isoformat()
        _safe_write_final_run_records(context)

        print("[RAW PIPELINE] X-Amplicon pipeline finished successfully.")
        return _build_pipeline_outputs(context)
    except Exception as exc:
        context.summary["status"] = "failed"
        context.summary["error"] = str(exc)
        context.summary["completed_at"] = datetime.now(timezone.utc).isoformat()
        if "sample_ids" in context.results:
            context.summary["sample_ids"] = context.results["sample_ids"]
        cleanup_summary = _cleanup_temporary_files(context.work_dirs["root"])
        if cleanup_summary["cleaned_paths"] or cleanup_summary["errors"]:
            context.summary["cleanup"] = cleanup_summary
        _safe_write_final_run_records(context)
        raise
