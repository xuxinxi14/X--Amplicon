"""CLI entrypoint for sequence_processor."""

from __future__ import annotations

import importlib
import json
import os

import click
import pandas as pd

from src.core.alpha_diversity import calculate_alpha_diversity, calculate_rarefaction_curve
from src.core.beta_diversity import (
    DEFAULT_BETA_METRICS as DEFAULT_NON_PHYLOGENETIC_BETA_METRICS,
    PHYLOGENETIC_BETA_METRICS,
    SUPPORTED_BETA_METRICS,
    calculate_beta_distance,
    normalize_beta_metric_name,
)
from src.core.database_registry import (
    DEFAULT_DATABASE_REGISTRY_PATH,
    check_database,
    list_databases,
    register_database as register_database_record,
    resolve_database_record,
)
from src.core.cli_only_workflow import build_cli_only_workflow, format_cli_only_workflow
from src.core.feature_filter import calculate_group_abundance

from src.core.otu_table_generator import (
    load_otutab_defaults,
    run_otutab_generation,
)
from src.core.otutab_filter import (
    ROUTE_16S,
    ROUTE_ITS,
    ROUTE_NONE,
    run_otutab_filter,
)
from src.core.otutab_rare import (
    run_otutab_rare,
)
from src.core.phylogenetic_tree import run_phylogenetic_tree_generation
from src.core.raw_amplicon_pipeline import (
    FEATURE_METHOD_ASV,
    FEATURE_METHOD_USEARCH_OTU,
    FEATURE_METHOD_VSEARCH_OTU,
    MERGE_BACKEND_PYTHON,
    MERGE_BACKEND_VSEARCH,
    VALID_FEATURE_METHODS,
    VALID_MERGE_BACKENDS,
    run_raw_amplicon_pipeline,
)
from src.core.taxonomy_summary import (
    parse_sintax_to_dataframe,
    summarize_taxa_abundance,
)
from src.core.stat_taxonomy import run_taxonomy_differential_abundance
from src.core.usearch_ASV_unoise3 import (
    load_usearch_asv_defaults,
    run_usearch_unoise3_denoising,
)
from src.core.usearch_otu_cluster import (
    load_usearch_otu_defaults,
    run_usearch_otu_clustering,
)
from src.core.vsearch_uchime_ref import (
    load_vsearch_uchime_ref_defaults,
    run_vsearch_uchime_ref,
)
from src.core.vsearch_sintax import (
    load_vsearch_sintax_defaults,
    resolve_sintax_database_path,
    run_vsearch_sintax,
)
from src.core.vsearch_otu_cluster import (
    DEFAULT_CONFIG_PATH,
    load_vsearch_otu_defaults,
    run_vsearch_otu_clustering,
)
from src.core.workflow_common import (
    DEFAULT_USEARCH_WINDOWS_PATH,
    DEFAULT_VSEARCH_WINDOWS_PATH,
    load_config_data,
    resolve_executable,
)
from src.utils.command_runner import CommandExecutionError
from src.utils.provenance import (
    PROVENANCE_SCHEMA_VERSION,
    build_provenance_record,
    write_json_record,
    write_provenance_markdown,
)
from agent.evaluation_logger import (
    export_evaluation_log,
    summarize_evaluation_log,
)

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}
DEFAULT_TAXONOMY_RANKS = (
    "Kingdom",
    "Phylum",
    "Class",
    "Order",
    "Family",
    "Genus",
    "Species",
)
PIPELINE_PARAMS_SECTION = "run_pipeline"
PIPELINE_REQUIRED_IMPORTS = ("Bio", "pydantic", "numpy", "pandas", "skbio")
VALID_CHIMERA_MODES = ("ref", "none")
VALID_OTUTAB_METHODS = ("usearch", "vsearch")
OPTIONAL_PATH_UNSET_TEXTS = {"none", "null"}
BETA_TREE_SKIP_TEXTS = {
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
PIPELINE_PARAM_ORDER = (
    "metadata_path",
    "seq_dir",
    "output_root",
    "read1_suffix",
    "read2_suffix",
    "merge_backend",
    "fastq_stripleft",
    "fastq_stripright",
    "fastq_maxee_rate",
    "feature_method",
    "feature_minsize",
    "feature_identity",
    "chimera_mode",
    "reference_db",
    "otutab_method",
    "otutab_identity",
    "annotation_database",
    "sintax_cutoff",
    "filter_route",
    "rarefaction_depth",
    "rarefaction_seed",
    "threads",
    "usearch_path",
    "vsearch_path",
    "command_timeout",
)


@click.group(context_settings=CONTEXT_SETTINGS)
def cli() -> None:
    """16S sequence processing CLI with VSEARCH and USEARCH workflows."""


def _read_table(path: str) -> pd.DataFrame:
    table = pd.read_csv(path, sep="\t", header=0, index_col=0)
    if table.empty:
        raise ValueError(f"Table is empty: {os.path.abspath(path)}")

    table.index = table.index.map(str)
    table.columns = table.columns.map(str)
    return table


def _read_metadata_table(path: str) -> pd.DataFrame:
    metadata = pd.read_csv(path, sep="\t", header=0, dtype=str)
    if metadata.empty:
        raise ValueError(f"Metadata table is empty: {os.path.abspath(path)}")

    first_column = str(metadata.columns[0])
    if "SampleID" not in metadata.columns:
        metadata = metadata.set_index(first_column, drop=False)

    return metadata


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


def _resolve_taxonomy_rank(rank: str) -> str:
    normalized_rank = str(rank).strip().lower()
    for candidate in DEFAULT_TAXONOMY_RANKS:
        if candidate.lower() == normalized_rank:
            return candidate

    raise ValueError(
        "rank must be one of: Kingdom, Phylum, Class, Order, Family, Genus, Species."
    )


def _require_config_value(config: dict[str, object], key: str) -> str:
    value = config.get(key)
    if value is None:
        raise ValueError(f"Missing required parameter in {PIPELINE_PARAMS_SECTION}: {key}")

    text = str(value).strip()
    if not text:
        raise ValueError(f"Missing required parameter in {PIPELINE_PARAMS_SECTION}: {key}")

    return text


def _get_optional_config_value(
    config: dict[str, object],
    key: str,
    default: str | None = None,
) -> str | None:
    value = config.get(key)
    if value is None:
        return default

    text = str(value).strip()
    if not text:
        return default

    return text


def _get_optional_path_config_value(
    config: dict[str, object],
    key: str,
    default: str | None = None,
) -> str | None:
    text = _get_optional_config_value(config, key, default)
    if text is None:
        return None
    if text.lower() in OPTIONAL_PATH_UNSET_TEXTS:
        return None
    return text


def _get_optional_tree_path_config_value(
    config: dict[str, object],
    key: str,
    default: str | None = None,
) -> str | None:
    text = _get_optional_path_config_value(config, key, default)
    if text is None:
        return None

    unquoted_text = text.strip("\"'`").strip()
    lowered = unquoted_text.lower()
    basename = os.path.basename(unquoted_text).lower()
    if lowered in BETA_TREE_SKIP_TEXTS or basename in BETA_TREE_SKIP_TEXTS:
        return None
    if os.path.isdir(unquoted_text):
        return None
    return unquoted_text


def _require_int_config_value(config: dict[str, object], key: str) -> int:
    try:
        return int(_require_config_value(config, key))
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer in {PIPELINE_PARAMS_SECTION}.") from exc


def _get_optional_int_config_value(
    config: dict[str, object],
    key: str,
    default: int,
) -> int:
    text = _get_optional_config_value(config, key)
    if text is None:
        return default

    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer in {PIPELINE_PARAMS_SECTION}.") from exc


def _require_float_config_value(config: dict[str, object], key: str) -> float:
    try:
        return float(_require_config_value(config, key))
    except ValueError as exc:
        raise ValueError(f"{key} must be a number in {PIPELINE_PARAMS_SECTION}.") from exc


def _get_optional_float_config_value(
    config: dict[str, object],
    key: str,
    default: float,
) -> float:
    text = _get_optional_config_value(config, key)
    if text is None:
        return default

    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"{key} must be a number in {PIPELINE_PARAMS_SECTION}.") from exc


def _get_optional_positive_float_config_value(
    config: dict[str, object],
    key: str,
) -> float | None:
    text = _get_optional_config_value(config, key)
    if text is None:
        return None

    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError(f"{key} must be a positive number in {PIPELINE_PARAMS_SECTION}.") from exc

    if value <= 0:
        raise ValueError(f"{key} must be a positive number in {PIPELINE_PARAMS_SECTION}.")

    return value


def _load_pipeline_params(params_path: str) -> dict[str, object]:
    resolved_params_path = os.path.abspath(params_path)
    loaded = load_config_data(resolved_params_path)
    if not isinstance(loaded, dict):
        raise ValueError(f"Invalid params file: {resolved_params_path}")

    config = loaded.get(PIPELINE_PARAMS_SECTION)
    if not isinstance(config, dict):
        raise ValueError(
            f"Params file must contain a '{PIPELINE_PARAMS_SECTION}' section: "
            f"{resolved_params_path}"
        )

    return {
        "metadata_path": _require_config_value(config, "metadata_path"),
        "seq_dir": _require_config_value(config, "seq_dir"),
        "output_root": _get_optional_config_value(config, "output_root", "work"),
        "read1_suffix": _get_optional_config_value(config, "read1_suffix", "_1.fq.gz"),
        "read2_suffix": _get_optional_config_value(config, "read2_suffix", "_2.fq.gz"),
        "merge_backend": _get_optional_config_value(
            config,
            "merge_backend",
            MERGE_BACKEND_VSEARCH,
        ),
        "fastq_stripleft": _require_int_config_value(config, "fastq_stripleft"),
        "fastq_stripright": _require_int_config_value(config, "fastq_stripright"),
        "fastq_maxee_rate": _require_float_config_value(config, "fastq_maxee_rate"),
        "feature_method": _get_optional_config_value(
            config,
            "feature_method",
            "usearch-asv",
        ),
        "feature_minsize": _get_optional_int_config_value(config, "feature_minsize", 10),
        "feature_identity": _get_optional_float_config_value(
            config,
            "feature_identity",
            0.97,
        ),
        "chimera_mode": _get_optional_config_value(config, "chimera_mode", "ref"),
        "reference_db": _get_optional_config_value(
            config,
            "reference_db",
            "database/rdp_16s_v18.fa",
        ),
        "otutab_method": _get_optional_config_value(config, "otutab_method", "usearch"),
        "otutab_identity": _get_optional_float_config_value(
            config,
            "otutab_identity",
            0.97,
        ),
        "annotation_database": _get_optional_config_value(
            config,
            "annotation_database",
            "rdp_16s_v18",
        ),
        "sintax_cutoff": _get_optional_float_config_value(config, "sintax_cutoff", 0.1),
        "filter_route": _get_optional_config_value(config, "filter_route", "16s"),
        "beta_tree_path": _get_optional_tree_path_config_value(config, "beta_tree_path"),
        "rarefaction_depth": _get_optional_int_config_value(config, "rarefaction_depth", 0),
        "rarefaction_seed": _get_optional_int_config_value(config, "rarefaction_seed", 1),
        "threads": _get_optional_int_config_value(config, "threads", 1),
        "usearch_path": _get_optional_path_config_value(config, "usearch_path"),
        "vsearch_path": _get_optional_path_config_value(config, "vsearch_path"),
        "command_timeout": _get_optional_positive_float_config_value(
            config,
            "command_timeout",
        ),
    }


def load_pipeline_params(params_path: str) -> dict[str, object]:
    """Load the run_pipeline section from a YAML params file."""

    return _load_pipeline_params(params_path)


def _make_pipeline_check_entry(
    name: str,
    status: str,
    message: str,
    **details: object,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "name": name,
        "status": status,
        "message": message,
    }
    if details:
        entry["details"] = details
    return entry


def _require_non_negative_int(name: str, value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer greater than or equal to 0.") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be an integer greater than or equal to 0.")
    return parsed


def _require_probability(name: str, value: object, *, allow_zero: bool) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number between 0 and 1.") from exc

    if allow_zero:
        if not 0 <= parsed <= 1:
            raise ValueError(f"{name} must be a number between 0 and 1.")
    elif not 0 < parsed <= 1:
        raise ValueError(f"{name} must be a number between 0 and 1.")

    return parsed


def _read_pipeline_sample_ids(metadata_path: str) -> list[str]:
    metadata = pd.read_csv(metadata_path, sep="\t", header=0, dtype=str)
    if metadata.empty:
        raise ValueError("metadata does not contain any sample rows.")

    sample_series = metadata.iloc[:, 0].fillna("").map(str).map(str.strip)
    sample_ids = [sample_id for sample_id in sample_series if sample_id]
    if len(sample_ids) != len(sample_series):
        raise ValueError("metadata contains an empty sample ID.")
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("metadata contains duplicate sample IDs.")
    return sample_ids


def _match_pipeline_read_pairs(
    seq_dir: str,
    sample_ids: list[str],
    read1_suffix: str,
    read2_suffix: str,
) -> tuple[int, list[str]]:
    missing: list[str] = []
    for sample_id in sample_ids:
        read1_path = os.path.join(seq_dir, f"{sample_id}{read1_suffix}")
        read2_path = os.path.join(seq_dir, f"{sample_id}{read2_suffix}")
        if not os.path.isfile(read1_path):
            missing.append(os.path.abspath(read1_path))
        if not os.path.isfile(read2_path):
            missing.append(os.path.abspath(read2_path))
    return len(sample_ids), missing


def _inspect_pipeline_config(params_path: str) -> dict[str, object]:
    resolved_params_path = os.path.abspath(params_path)
    pipeline_params = _load_pipeline_params(resolved_params_path)
    return inspect_pipeline_params_dict(
        pipeline_params,
        params_source=resolved_params_path,
    )


def _resolve_database_summary_path(value: object) -> str:
    try:
        record = resolve_database_record(
            str(value),
            require_exists=False,
            include_hash=False,
        )
    except (KeyError, ValueError):
        return os.path.abspath(str(value))
    return os.path.abspath(str(record.get("path") or value))


def _build_pipeline_effective_params(
    pipeline_params: dict[str, object],
    *,
    params_source: str | None,
) -> dict[str, object]:
    return {
        "metadata_path": os.path.abspath(str(pipeline_params["metadata_path"])),
        "seq_dir": os.path.abspath(str(pipeline_params["seq_dir"])),
        "output_root": os.path.abspath(str(pipeline_params["output_root"])),
        "read1_suffix": str(pipeline_params["read1_suffix"]),
        "read2_suffix": str(pipeline_params["read2_suffix"]),
        "merge_backend": str(
            pipeline_params.get("merge_backend", MERGE_BACKEND_VSEARCH)
        ).strip().lower(),
        "fastq_stripleft": pipeline_params["fastq_stripleft"],
        "fastq_stripright": pipeline_params["fastq_stripright"],
        "fastq_maxee_rate": pipeline_params["fastq_maxee_rate"],
        "feature_minsize": pipeline_params["feature_minsize"],
        "feature_method": str(pipeline_params["feature_method"]).strip().lower(),
        "feature_identity": pipeline_params["feature_identity"],
        "chimera_mode": str(pipeline_params["chimera_mode"]).strip().lower(),
        "reference_db": _resolve_database_summary_path(pipeline_params["reference_db"]),
        "otutab_method": str(pipeline_params["otutab_method"]).strip().lower(),
        "otutab_identity": pipeline_params["otutab_identity"],
        "annotation_database": str(pipeline_params["annotation_database"]).strip(),
        "sintax_cutoff": pipeline_params["sintax_cutoff"],
        "filter_route": str(pipeline_params["filter_route"]).strip().lower(),
        "beta_tree_path": (
            None
            if pipeline_params.get("beta_tree_path") is None
            else os.path.abspath(str(pipeline_params["beta_tree_path"]))
        ),
        "rarefaction_depth": pipeline_params["rarefaction_depth"],
        "rarefaction_seed": pipeline_params["rarefaction_seed"],
        "threads": pipeline_params["threads"],
        "usearch_path": (
            None
            if pipeline_params["usearch_path"] is None
            else os.path.abspath(str(pipeline_params["usearch_path"]))
        ),
        "vsearch_path": (
            None
            if pipeline_params["vsearch_path"] is None
            else os.path.abspath(str(pipeline_params["vsearch_path"]))
        ),
        "command_timeout": pipeline_params["command_timeout"],
        "params_source": None if params_source is None else os.path.abspath(params_source),
    }


def inspect_pipeline_params_dict(
    pipeline_params: dict[str, object],
    *,
    params_source: str | None,
) -> dict[str, object]:
    resolved_params_path = (
        os.path.abspath(params_source)
        if params_source is not None
        else "(session overrides)"
    )
    checks: list[dict[str, object]] = []
    errors: list[str] = []

    effective_params = _build_pipeline_effective_params(
        pipeline_params,
        params_source=params_source,
    )

    imported_modules: list[str] = []
    missing_modules: list[str] = []
    for module_name in PIPELINE_REQUIRED_IMPORTS:
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            missing_modules.append(module_name)
        else:
            imported_modules.append(module_name)
    if missing_modules:
        message = "Missing Python modules: " + ", ".join(missing_modules)
        errors.append(message)
        checks.append(
            _make_pipeline_check_entry(
                "python_dependencies",
                "failed",
                message,
                imported=imported_modules,
                missing=missing_modules,
            )
        )
    else:
        checks.append(
            _make_pipeline_check_entry(
                "python_dependencies",
                "passed",
                "All required Python modules import successfully.",
                imported=imported_modules,
            )
        )

    try:
        feature_method = effective_params["feature_method"]
        if feature_method not in VALID_FEATURE_METHODS:
            raise ValueError(
                "feature_method must be one of: "
                f"{', '.join(sorted(VALID_FEATURE_METHODS))}."
            )
        merge_backend = effective_params["merge_backend"]
        if merge_backend not in VALID_MERGE_BACKENDS:
            raise ValueError("merge_backend must be one of: vsearch, python.")
        chimera_mode = effective_params["chimera_mode"]
        if chimera_mode not in VALID_CHIMERA_MODES:
            raise ValueError("chimera_mode must be one of: ref, none.")
        otutab_method = effective_params["otutab_method"]
        if otutab_method not in VALID_OTUTAB_METHODS:
            raise ValueError("otutab_method must be one of: usearch, vsearch.")
        filter_route = effective_params["filter_route"]
        if filter_route not in {ROUTE_16S, ROUTE_ITS, ROUTE_NONE}:
            raise ValueError("filter_route must be one of: 16s, its, none.")

        effective_params["fastq_stripleft"] = _require_non_negative_int(
            "fastq_stripleft", effective_params["fastq_stripleft"]
        )
        effective_params["fastq_stripright"] = _require_non_negative_int(
            "fastq_stripright", effective_params["fastq_stripright"]
        )
        effective_params["feature_minsize"] = int(effective_params["feature_minsize"])
        if effective_params["feature_minsize"] < 1:
            raise ValueError("feature_minsize must be an integer greater than or equal to 1.")
        effective_params["threads"] = int(effective_params["threads"])
        if effective_params["threads"] < 1:
            raise ValueError("threads must be an integer greater than or equal to 1.")
        effective_params["rarefaction_depth"] = _require_non_negative_int(
            "rarefaction_depth",
            effective_params["rarefaction_depth"],
        )
        effective_params["rarefaction_seed"] = int(effective_params["rarefaction_seed"])
        if effective_params["rarefaction_seed"] < 0:
            raise ValueError("rarefaction_seed must be an integer greater than or equal to 0.")
        effective_params["fastq_maxee_rate"] = float(effective_params["fastq_maxee_rate"])
        if effective_params["fastq_maxee_rate"] < 0:
            raise ValueError("fastq_maxee_rate must be greater than or equal to 0.")
        effective_params["feature_identity"] = _require_probability(
            "feature_identity",
            effective_params["feature_identity"],
            allow_zero=False,
        )
        effective_params["otutab_identity"] = _require_probability(
            "otutab_identity",
            effective_params["otutab_identity"],
            allow_zero=False,
        )
        effective_params["sintax_cutoff"] = _require_probability(
            "sintax_cutoff",
            effective_params["sintax_cutoff"],
            allow_zero=True,
        )
        checks.append(
            _make_pipeline_check_entry(
                "pipeline_parameters",
                "passed",
                "Core pipeline parameters are syntactically valid.",
                feature_method=feature_method,
                merge_backend=merge_backend,
                otutab_method=otutab_method,
                filter_route=filter_route,
                threads=effective_params["threads"],
                rarefaction_depth=effective_params["rarefaction_depth"],
                rarefaction_seed=effective_params["rarefaction_seed"],
            )
        )
    except ValueError as exc:
        errors.append(str(exc))
        checks.append(
            _make_pipeline_check_entry(
                "pipeline_parameters",
                "failed",
                str(exc),
            )
        )

    metadata_path = str(effective_params["metadata_path"])
    sample_ids: list[str] = []
    if os.path.isfile(metadata_path):
        try:
            sample_ids = _read_pipeline_sample_ids(metadata_path)
        except ValueError as exc:
            errors.append(str(exc))
            checks.append(
                _make_pipeline_check_entry(
                    "metadata",
                    "failed",
                    str(exc),
                    metadata_path=metadata_path,
                )
            )
        else:
            checks.append(
                _make_pipeline_check_entry(
                    "metadata",
                    "passed",
                    "Metadata file exists and sample IDs are readable.",
                    metadata_path=metadata_path,
                    sample_count=len(sample_ids),
                )
            )
    else:
        message = f"metadata_path not found: {metadata_path}"
        errors.append(message)
        checks.append(
            _make_pipeline_check_entry(
                "metadata",
                "failed",
                message,
                metadata_path=metadata_path,
            )
        )

    seq_dir = str(effective_params["seq_dir"])
    if os.path.isdir(seq_dir):
        checks.append(
            _make_pipeline_check_entry(
                "sequence_directory",
                "passed",
                "Sequence directory exists.",
                seq_dir=seq_dir,
            )
        )
    else:
        message = f"seq_dir not found: {seq_dir}"
        errors.append(message)
        checks.append(
            _make_pipeline_check_entry(
                "sequence_directory",
                "failed",
                message,
                seq_dir=seq_dir,
            )
        )

    if sample_ids and os.path.isdir(seq_dir):
        matched_pair_count, missing_pairs = _match_pipeline_read_pairs(
            seq_dir=seq_dir,
            sample_ids=sample_ids,
            read1_suffix=str(effective_params["read1_suffix"]),
            read2_suffix=str(effective_params["read2_suffix"]),
        )
        if missing_pairs:
            message = (
                "Missing paired-end FASTQ files for one or more metadata samples."
            )
            errors.append(message)
            checks.append(
                _make_pipeline_check_entry(
                    "sample_fastq_pairs",
                    "failed",
                    message,
                    missing=missing_pairs,
                )
            )
        else:
            checks.append(
                _make_pipeline_check_entry(
                    "sample_fastq_pairs",
                    "passed",
                    "All metadata samples match paired-end FASTQ files.",
                    matched_pairs=matched_pair_count,
                )
            )

    reference_db_path = str(effective_params["reference_db"])
    if effective_params["chimera_mode"] == "ref":
        reference_check = check_database(reference_db_path, include_hash=False)
        if reference_check["status"] == "passed":
            checks.append(
                _make_pipeline_check_entry(
                    "reference_database",
                    "passed",
                    "Reference database exists for chimera filtering.",
                    reference_db=reference_check.get("path", reference_db_path),
                    database_name=reference_check.get("name"),
                    database_version=reference_check.get("version"),
                    database_source=reference_check.get("source"),
                )
            )
        else:
            message = str(reference_check.get("message") or f"reference_db not found: {reference_db_path}")
            errors.append(message)
            checks.append(
                _make_pipeline_check_entry(
                    "reference_database",
                    "failed",
                    message,
                    reference_db=reference_check.get("path", reference_db_path),
                    database_name=reference_check.get("name"),
                )
            )
    else:
        checks.append(
            _make_pipeline_check_entry(
                "reference_database",
                "skipped",
                "chimera_mode=none, so reference_db is not required.",
                reference_db=reference_db_path,
            )
        )

    try:
        resolved_database_name, resolved_database_path = resolve_sintax_database_path(
            str(effective_params["annotation_database"])
        )
    except (FileNotFoundError, ValueError) as exc:
        errors.append(str(exc))
        checks.append(
            _make_pipeline_check_entry(
                "annotation_database",
                "failed",
                str(exc),
                annotation_database=effective_params["annotation_database"],
            )
        )
    else:
        annotation_check = check_database(resolved_database_path, include_hash=False)
        effective_params["annotation_database"] = resolved_database_name
        effective_params["annotation_database_path"] = resolved_database_path
        checks.append(
            _make_pipeline_check_entry(
                "annotation_database",
                "passed",
                "Annotation database resolves to an existing FASTA file.",
                annotation_database=resolved_database_name,
                database_path=resolved_database_path,
                database_version=annotation_check.get("version"),
                taxonomy_format=annotation_check.get("taxonomy_format"),
                database_source=annotation_check.get("source"),
            )
        )

    beta_tree_path = effective_params["beta_tree_path"]
    if beta_tree_path is not None and os.path.isfile(str(beta_tree_path)):
        checks.append(
            _make_pipeline_check_entry(
                "beta_tree_path",
                "passed",
                "beta_tree_path exists; UniFrac outputs can be generated.",
                beta_tree_path=beta_tree_path,
            )
        )
    elif beta_tree_path is not None:
        message = f"beta_tree_path not found: {beta_tree_path}"
        errors.append(message)
        checks.append(
            _make_pipeline_check_entry(
                "beta_tree_path",
                "failed",
                message,
                beta_tree_path=beta_tree_path,
            )
        )

    requires_usearch = effective_params["feature_method"] in {
        FEATURE_METHOD_ASV,
        FEATURE_METHOD_USEARCH_OTU,
    } or effective_params["otutab_method"] == "usearch"
    usearch_label = "required" if requires_usearch else "optional"
    try:
        resolved_usearch = resolve_executable(
            executable_name="usearch",
            configured_path=(
                None
                if effective_params["usearch_path"] is None
                else str(effective_params["usearch_path"])
            ),
            windows_default_path=DEFAULT_USEARCH_WINDOWS_PATH,
            label="USEARCH",
        )
    except FileNotFoundError as exc:
        if requires_usearch:
            errors.append(str(exc))
            status = "failed"
            message = str(exc)
        else:
            status = "skipped"
            message = "USEARCH is not required by the current pipeline settings."
        checks.append(
            _make_pipeline_check_entry(
                "usearch_executable",
                status,
                message,
                requirement=usearch_label,
            )
        )
    else:
        effective_params["usearch_path"] = resolved_usearch
        checks.append(
            _make_pipeline_check_entry(
                "usearch_executable",
                "passed",
                "USEARCH executable is available.",
                requirement=usearch_label,
                usearch_path=resolved_usearch,
            )
        )

    try:
        resolved_vsearch = resolve_executable(
            executable_name="vsearch",
            configured_path=(
                None
                if effective_params["vsearch_path"] is None
                else str(effective_params["vsearch_path"])
            ),
            windows_default_path=DEFAULT_VSEARCH_WINDOWS_PATH,
            label="VSEARCH",
        )
    except FileNotFoundError as exc:
        errors.append(str(exc))
        checks.append(
            _make_pipeline_check_entry(
                "vsearch_executable",
                "failed",
                str(exc),
            )
        )
    else:
        effective_params["vsearch_path"] = resolved_vsearch
        checks.append(
            _make_pipeline_check_entry(
                "vsearch_executable",
                "passed",
                "VSEARCH executable is available.",
                vsearch_path=resolved_vsearch,
            )
        )

    planned_beta_metrics = list(DEFAULT_NON_PHYLOGENETIC_BETA_METRICS)
    planned_beta_metrics.extend(PHYLOGENETIC_BETA_METRICS)

    report = {
        "status": "passed" if not errors else "failed",
        "params_path": resolved_params_path,
        "effective_params": effective_params,
        "checks": checks,
        "errors": errors,
        "planned_outputs": {
            "final_dir": os.path.join(str(effective_params["output_root"]), "06_final"),
            "run_summary": os.path.join(
                str(effective_params["output_root"]),
                "06_final",
                "run_summary.json",
            ),
            "provenance_json": os.path.join(
                str(effective_params["output_root"]),
                "06_final",
                "provenance.json",
            ),
            "provenance_md": os.path.join(
                str(effective_params["output_root"]),
                "06_final",
                "provenance.md",
            ),
            "rarefied_otutab": os.path.join(
                str(effective_params["output_root"]),
                "06_final",
                "otutab_rare.txt",
            ),
            "alpha_rarefaction": os.path.join(
                str(effective_params["output_root"]),
                "06_final",
                "alpha",
                "alpha_rarefaction.tsv",
            ),
            "phylogenetic_tree": (
                effective_params["beta_tree_path"]
                or os.path.join(str(effective_params["output_root"]), "06_final", "otus.tree")
            ),
            "beta_metrics": planned_beta_metrics,
        },
        "skipped_optional_steps": [],
    }
    return report


def _echo_pipeline_check_report(report: dict[str, object]) -> None:
    status = str(report["status"]).upper()
    click.echo(f"[CLI] Pipeline config check: {status}")
    click.echo(f"[CLI] Params file: {report['params_path']}")

    effective_params = report["effective_params"]
    assert isinstance(effective_params, dict)
    click.echo(f"[CLI] Metadata: {effective_params['metadata_path']}")
    click.echo(f"[CLI] Sequence directory: {effective_params['seq_dir']}")
    click.echo(f"[CLI] Output root: {effective_params['output_root']}")
    click.echo(f"[CLI] Feature method: {effective_params['feature_method']}")
    click.echo(f"[CLI] Merge backend: {effective_params['merge_backend']}")
    click.echo(f"[CLI] OTU table method: {effective_params['otutab_method']}")
    click.echo(f"[CLI] Annotation database: {effective_params['annotation_database']}")
    if effective_params.get("annotation_database_path"):
        click.echo(f"[CLI] Annotation database path: {effective_params['annotation_database_path']}")
    click.echo(f"[CLI] Filter route: {effective_params['filter_route']}")
    click.echo(f"[CLI] Rarefaction depth: {effective_params['rarefaction_depth']}")
    click.echo(f"[CLI] Rarefaction seed: {effective_params['rarefaction_seed']}")

    for check in report["checks"]:
        assert isinstance(check, dict)
        click.echo(
            f"[CLI] [{str(check['status']).upper()}] {check['name']}: {check['message']}"
        )

    planned_outputs = report["planned_outputs"]
    assert isinstance(planned_outputs, dict)
    click.echo(f"[CLI] Planned final directory: {planned_outputs['final_dir']}")
    click.echo(f"[CLI] Planned run summary: {planned_outputs['run_summary']}")
    click.echo(f"[CLI] Planned provenance JSON: {planned_outputs['provenance_json']}")
    click.echo(f"[CLI] Planned provenance Markdown: {planned_outputs['provenance_md']}")
    click.echo(f"[CLI] Planned rarefied OTU table: {planned_outputs['rarefied_otutab']}")
    click.echo(f"[CLI] Planned alpha rarefaction: {planned_outputs['alpha_rarefaction']}")
    click.echo(f"[CLI] Planned phylogenetic tree: {planned_outputs['phylogenetic_tree']}")
    click.echo(
        "[CLI] Planned beta metrics: "
        + ", ".join(str(metric) for metric in planned_outputs["beta_metrics"])
    )


@cli.command("cli-only-workflow")
@click.option(
    "--params",
    "params_path",
    default="pipeline_params.yaml",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Pipeline params YAML path used by the deterministic workflow.",
)
@click.option(
    "--output-root",
    default="work",
    show_default=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Pipeline output root directory.",
)
@click.option(
    "--final-dir",
    default=None,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Completed final directory. Defaults to <output-root>/06_final.",
)
@click.option(
    "--no-optional",
    is_flag=True,
    help="Show only database, preflight, full pipeline, and provenance commands.",
)
def cli_only_workflow_command(
    params_path: str,
    output_root: str,
    final_dir: str | None,
    no_optional: bool,
) -> None:
    """Print a deterministic workflow that does not require an LLM."""

    workflow = build_cli_only_workflow(
        params_path=params_path,
        output_root=output_root,
        final_dir=final_dir,
        include_optional=not no_optional,
    )
    click.echo(format_cli_only_workflow(workflow))


def _format_database_hash(record: dict[str, object]) -> str:
    observed = record.get("sha256")
    expected = record.get("expected_sha256")
    value = observed if isinstance(observed, str) and observed else expected
    if not isinstance(value, str) or not value:
        return "NA"
    return value[:12]


def _echo_database_record(record: dict[str, object]) -> None:
    click.echo(f"[CLI] Name: {record.get('name', 'NA')}")
    click.echo(f"[CLI] Status: {record.get('status', 'unknown')}")
    click.echo(f"[CLI] Message: {record.get('message', 'NA')}")
    click.echo(f"[CLI] Version: {record.get('version', 'NA')}")
    click.echo(f"[CLI] Type: {record.get('type', 'NA')}")
    click.echo(f"[CLI] Taxonomy format: {record.get('taxonomy_format', 'NA')}")
    click.echo(f"[CLI] Source: {record.get('source', 'NA')}")
    click.echo(f"[CLI] Path: {record.get('path', 'NA')}")
    click.echo(f"[CLI] Size bytes: {record.get('size_bytes', 'NA')}")
    click.echo(f"[CLI] SHA-256: {record.get('sha256') or record.get('expected_sha256') or 'NA'}")
    if "hash_matches" in record:
        click.echo(f"[CLI] Hash matches: {record['hash_matches']}")


@cli.command("list-databases")
@click.option(
    "--registry",
    "registry_path",
    default=os.path.basename(DEFAULT_DATABASE_REGISTRY_PATH),
    show_default=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Database registry YAML path.",
)
@click.option(
    "--builtins/--no-builtins",
    "include_builtin",
    default=True,
    show_default=True,
    help="Include built-in RDP/SILVA compatibility records.",
)
@click.option(
    "--with-hash",
    "include_hash",
    is_flag=True,
    help="Calculate SHA-256 hashes while listing databases.",
)
def list_databases_command(
    registry_path: str,
    include_builtin: bool,
    include_hash: bool,
) -> None:
    """List registered reference databases."""

    try:
        records = list_databases(
            registry_path=registry_path,
            include_builtin=include_builtin,
            include_hash=include_hash,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"[CLI] Registry: {os.path.abspath(registry_path)}")
    if not os.path.exists(os.path.abspath(registry_path)):
        click.echo("[CLI] Registry file does not exist; showing built-in records only.")
    click.echo("[CLI] name\tversion\ttype\tformat\texists\thash\tpath")
    for record in records:
        click.echo(
            "[CLI] "
            + "\t".join(
                [
                    str(record.get("name", "NA")),
                    str(record.get("version", "NA")),
                    str(record.get("type", "NA")),
                    str(record.get("taxonomy_format", "NA")),
                    str(record.get("exists", "NA")),
                    _format_database_hash(record),
                    str(record.get("path", "NA")),
                ]
            )
        )


@cli.command("check-database")
@click.argument("database", type=str)
@click.option(
    "--registry",
    "registry_path",
    default=os.path.basename(DEFAULT_DATABASE_REGISTRY_PATH),
    show_default=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Database registry YAML path.",
)
@click.option(
    "--with-hash/--no-hash",
    "include_hash",
    default=True,
    show_default=True,
    help="Calculate and verify SHA-256 when possible.",
)
def check_database_command(
    database: str,
    registry_path: str,
    include_hash: bool,
) -> None:
    """Check a registered database name, alias, or FASTA path."""

    try:
        record = check_database(
            database,
            registry_path=registry_path,
            include_hash=include_hash,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    _echo_database_record(record)
    if record.get("status") != "passed":
        raise click.ClickException(str(record.get("message") or "Database check failed."))


@cli.command("register-database")
@click.option("--name", required=True, type=str, help="Database registry name.")
@click.option(
    "--path",
    "sequence_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Reference FASTA path.",
)
@click.option("--version", default=None, type=str, help="Database version label.")
@click.option(
    "--taxonomy-format",
    default="sintax",
    show_default=True,
    type=str,
    help="Taxonomy format, for example sintax.",
)
@click.option(
    "--type",
    "database_type",
    default="taxonomy_annotation",
    show_default=True,
    type=str,
    help="Database type label.",
)
@click.option(
    "--registry",
    "registry_path",
    default=os.path.basename(DEFAULT_DATABASE_REGISTRY_PATH),
    show_default=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Database registry YAML path to create or update.",
)
@click.option("--alias", "aliases", multiple=True, type=str, help="Optional alias.")
@click.option("--role", "roles", multiple=True, type=str, help="Optional role label.")
@click.option("--sha256", default=None, type=str, help="Known SHA-256 checksum.")
@click.option(
    "--compute-hash/--no-hash",
    "compute_hash",
    default=True,
    show_default=True,
    help="Calculate SHA-256 while registering.",
)
@click.option(
    "--allow-missing",
    is_flag=True,
    help="Allow registering a path that does not exist yet.",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Overwrite an existing record with the same name.",
)
def register_database_command(
    name: str,
    sequence_path: str,
    version: str | None,
    taxonomy_format: str,
    database_type: str,
    registry_path: str,
    aliases: tuple[str, ...],
    roles: tuple[str, ...],
    sha256: str | None,
    compute_hash: bool,
    allow_missing: bool,
    overwrite: bool,
) -> None:
    """Register a database FASTA in databases.yaml."""

    try:
        record = register_database_record(
            name=name,
            sequence_path=sequence_path,
            version=version,
            taxonomy_format=taxonomy_format,
            database_type=database_type,
            registry_path=registry_path,
            aliases=list(aliases),
            roles=list(roles) if roles else None,
            sha256=sha256,
            compute_hash=compute_hash,
            require_exists=not allow_missing,
            overwrite=overwrite,
        )
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] Database registered successfully.")
    click.echo(f"[CLI] Registry: {os.path.abspath(registry_path)}")
    _echo_database_record(record)


@cli.command("write-provenance")
@click.option(
    "--summary",
    "summary_path",
    default=os.path.join("work", "06_final", "run_summary.json"),
    show_default=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Existing run_summary.json to convert into a provenance record.",
)
@click.option(
    "--output-json",
    "output_json",
    default=None,
    type=click.Path(dir_okay=False, writable=True, path_type=str),
    help="Output provenance JSON path. Defaults to <summary_dir>/provenance.json.",
)
@click.option(
    "--output-md",
    "output_md",
    default=None,
    type=click.Path(dir_okay=False, writable=True, path_type=str),
    help="Output provenance Markdown path. Defaults to <summary_dir>/provenance.md.",
)
def write_provenance(summary_path: str, output_json: str | None, output_md: str | None) -> None:
    """Generate or refresh provenance files from an existing run summary."""

    resolved_summary_path = os.path.abspath(summary_path)
    final_dir = os.path.dirname(resolved_summary_path)
    provenance_json_path = os.path.abspath(output_json or os.path.join(final_dir, "provenance.json"))
    provenance_md_path = os.path.abspath(output_md or os.path.join(final_dir, "provenance.md"))

    try:
        with open(resolved_summary_path, "r", encoding="utf-8") as handle:
            summary = json.load(handle)
        if not isinstance(summary, dict):
            raise ValueError("run_summary.json must contain a JSON object.")

        summary["summary_path"] = resolved_summary_path
        summary["provenance_path"] = provenance_json_path
        summary["provenance_md_path"] = provenance_md_path
        provenance = build_provenance_record(
            project_root=os.path.dirname(os.path.abspath(__file__)),
            summary=summary,
            provenance_path=provenance_json_path,
            provenance_md_path=provenance_md_path,
        )
        written_json = write_json_record(provenance, provenance_json_path)
        written_md = write_provenance_markdown(provenance, provenance_md_path)
        summary["provenance"] = {
            "schema_version": PROVENANCE_SCHEMA_VERSION,
            "generated_at": provenance["generated_at"],
            "json": written_json,
            "markdown": written_md,
        }
        with open(resolved_summary_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(summary, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] Provenance record generated successfully.")
    click.echo(f"[CLI] Run summary: {resolved_summary_path}")
    click.echo(f"[CLI] Provenance JSON: {written_json}")
    click.echo(f"[CLI] Provenance Markdown: {written_md}")


@cli.command("generate-report")
@click.option(
    "--final-dir",
    default=os.path.join("work", "06_final"),
    show_default=True,
    type=click.Path(exists=True, file_okay=False, readable=True, path_type=str),
    help="Completed pipeline final directory.",
)
@click.option(
    "--summary",
    "summary_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Optional run_summary.json path. Defaults to <final-dir>/run_summary.json.",
)
@click.option(
    "--provenance",
    "provenance_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Optional provenance.json path. Defaults to the path recorded in run_summary.json.",
)
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(file_okay=False, dir_okay=True, writable=True, path_type=str),
    help="Report output directory. Defaults to <final-dir>/report.",
)
@click.option("--no-html", is_flag=True, help="Only write Markdown and report data JSON.")
@click.option("--no-figures", is_flag=True, help="Do not include figure links or embedded HTML figures.")
@click.option("--top-taxa", default=10, show_default=True, type=int, help="Top taxa per reported taxonomy level.")
def generate_report(
    final_dir: str,
    summary_path: str | None,
    provenance_path: str | None,
    output_dir: str | None,
    no_html: bool,
    no_figures: bool,
    top_taxa: int,
) -> None:
    """Generate a Markdown/HTML analysis report for a completed run."""

    try:
        from src.core.report_generator import generate_analysis_report

        result = generate_analysis_report(
            final_dir=final_dir,
            summary_path=summary_path,
            provenance_path=provenance_path,
            output_dir=output_dir,
            include_html=not no_html,
            include_figures=not no_figures,
            top_taxa=top_taxa,
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] Analysis report generated successfully.")
    click.echo(f"[CLI] Output directory: {result.get('output_dir')}")
    click.echo(f"[CLI] Markdown report: {result.get('markdown')}")
    if result.get("html"):
        click.echo(f"[CLI] HTML report: {result.get('html')}")
    click.echo(f"[CLI] Report data JSON: {result.get('data')}")
    click.echo(f"[CLI] Embedded/linkable figures: {len(result.get('figures') or [])}")


cli.add_command(generate_report, "report")


@cli.command("agent-evaluation-log")
@click.option(
    "--log-path",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional Agent evaluation JSONL path. Defaults to run_logs/agent_evaluation_log.jsonl.",
)
@click.option("--limit", default=20, show_default=True, type=int, help="Recent event count to print.")
@click.option(
    "--export-json",
    default=None,
    type=click.Path(dir_okay=False, writable=True, path_type=str),
    help="Optional path to export all JSONL events as one JSON document.",
)
def agent_evaluation_log(
    log_path: str | None,
    limit: int,
    export_json: str | None,
) -> None:
    """Summarize or export Agent task/tool evaluation logs."""

    try:
        summary = summarize_evaluation_log(log_path=log_path, limit=limit)
        exported = (
            export_evaluation_log(output_path=export_json, log_path=log_path)
            if export_json
            else None
        )
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] Agent evaluation log summary")
    click.echo(f"[CLI] Log path: {summary.get('log_path')}")
    click.echo(f"[CLI] Events: {summary.get('event_count')}")
    click.echo(f"[CLI] User tasks: {summary.get('task_count')}")
    click.echo(f"[CLI] Tool calls: {summary.get('tool_call_count')}")
    click.echo(
        "[CLI] Status counts: "
        + json.dumps(summary.get("status_counts", {}), ensure_ascii=False, sort_keys=True)
    )
    click.echo(
        "[CLI] Error types: "
        + json.dumps(summary.get("error_type_counts", {}), ensure_ascii=False, sort_keys=True)
    )
    click.echo(
        "[CLI] Recovery paths: "
        + json.dumps(summary.get("recovery_path_counts", {}), ensure_ascii=False, sort_keys=True)
    )
    if exported is not None:
        click.echo(f"[CLI] Exported JSON: {exported.get('output_path')}")


cli.add_command(agent_evaluation_log, "agent-eval-log")


@cli.command("check-pipeline-config")
@click.option(
    "--params",
    "params_path",
    default="pipeline_params.yaml",
    show_default=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="YAML parameter file used to validate the integrated raw FASTQ pipeline.",
)
def check_pipeline_config(params_path: str) -> None:
    """Validate pipeline params, inputs, and required executables without running."""

    try:
        report = _inspect_pipeline_config(params_path)
    except (FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    _echo_pipeline_check_report(report)
    if report["status"] != "passed":
        errors = report["errors"]
        assert isinstance(errors, list)
        raise click.ClickException("\n".join(str(error) for error in errors))


@cli.command("run-pipeline")
@click.option(
    "--metadata",
    "metadata_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Metadata table whose first column contains sample IDs.",
)
@click.option(
    "--seq-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False, readable=True, path_type=str),
    help="Directory containing raw paired FASTQ files.",
)
@click.option(
    "--output-root",
    default="work",
    show_default=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Output root directory for the staged workflow files.",
)
@click.option(
    "--read1-suffix",
    default="_1.fq.gz",
    show_default=True,
    type=str,
    help="Suffix appended to each sample ID to locate read 1 files.",
)
@click.option(
    "--read2-suffix",
    default="_2.fq.gz",
    show_default=True,
    type=str,
    help="Suffix appended to each sample ID to locate read 2 files.",
)
@click.option(
    "--merge-backend",
    default=MERGE_BACKEND_VSEARCH,
    show_default=True,
    type=click.Choice(
        [MERGE_BACKEND_VSEARCH, MERGE_BACKEND_PYTHON],
        case_sensitive=False,
    ),
    help="Backend used to merge paired-end FASTQ reads.",
)
@click.option(
    "--fastq-stripleft",
    required=True,
    type=click.IntRange(min=0),
    help="Left trimming length passed to the FASTQ filtering stage.",
)
@click.option(
    "--fastq-stripright",
    required=True,
    type=click.IntRange(min=0),
    help="Right trimming length passed to the FASTQ filtering stage.",
)
@click.option(
    "--fastq-maxee-rate",
    required=True,
    type=float,
    help="Maximum expected error rate passed to the FASTQ filtering stage.",
)
@click.option(
    "--feature-method",
    default="usearch-asv",
    show_default=True,
    type=click.Choice(["usearch-asv", "usearch-otu", "vsearch-otu"], case_sensitive=False),
    help="Feature generation method used after dereplication.",
)
@click.option(
    "--feature-minsize",
    default=10,
    show_default=True,
    type=click.IntRange(min=1),
    help="Minimum abundance threshold shared by dereplication and feature generation.",
)
@click.option(
    "--feature-identity",
    default=0.97,
    show_default=True,
    type=float,
    help="Identity threshold used only by the vsearch-otu feature method.",
)
@click.option(
    "--chimera-mode",
    default="ref",
    show_default=True,
    type=click.Choice(["ref", "none"], case_sensitive=False),
    help="Chimera handling mode before otutab and annotation.",
)
@click.option(
    "--reference-db",
    default="database/rdp_16s_v18.fa",
    show_default=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Reference FASTA used by the uchime_ref stage when chimera mode is ref.",
)
@click.option(
    "--otutab-method",
    default="usearch",
    show_default=True,
    type=click.Choice(["usearch", "vsearch"], case_sensitive=False),
    help="Backend used to generate the raw feature table.",
)
@click.option(
    "--otutab-identity",
    default=0.97,
    show_default=True,
    type=float,
    help="Identity threshold used only when otutab method is vsearch.",
)
@click.option(
    "--annotation-database",
    default="rdp_16s_v18",
    show_default=True,
    type=str,
    help="Annotation database preset used by vsearch-sintax.",
)
@click.option(
    "--sintax-cutoff",
    default=0.1,
    show_default=True,
    type=float,
    help="Confidence cutoff used by vsearch-sintax.",
)
@click.option(
    "--filter-route",
    default="16s",
    show_default=True,
    type=click.Choice(["16s", "its", "none"], case_sensitive=False),
    help="Final taxonomy filtering route.",
)
@click.option(
    "--beta-tree",
    "beta_tree_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    hidden=True,
    help="Optional legacy rooted tree override for UniFrac beta diversity outputs.",
)
@click.option(
    "--rarefaction-depth",
    default=0,
    show_default=True,
    type=click.IntRange(min=0),
    help="Rarefaction depth used to create the equal-sampling OTU table. Use 0 to select the minimum sample depth automatically.",
)
@click.option(
    "--rarefaction-seed",
    default=1,
    show_default=True,
    type=click.IntRange(min=0),
    help="Random seed used for equal-sampling OTU table generation and alpha rarefaction.",
)
@click.option(
    "--threads",
    default=1,
    show_default=True,
    type=click.IntRange(min=1),
    help="Thread count shared by the USEARCH/VSEARCH stages.",
)
@click.option(
    "--command-timeout",
    default=None,
    type=click.FloatRange(min=0, min_open=True),
    help="Optional timeout in seconds applied to each USEARCH/VSEARCH command.",
)
@click.option(
    "--usearch-path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    help="Optional explicit path to the USEARCH executable.",
)
@click.option(
    "--vsearch-path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    help="Optional explicit path to the VSEARCH executable.",
)
def run_pipeline(
    metadata_path: str,
    seq_dir: str,
    output_root: str,
    read1_suffix: str,
    read2_suffix: str,
    merge_backend: str,
    fastq_stripleft: int,
    fastq_stripright: int,
    fastq_maxee_rate: float,
    feature_method: str,
    feature_minsize: int,
    feature_identity: float,
    chimera_mode: str,
    reference_db: str,
    otutab_method: str,
    otutab_identity: float,
    annotation_database: str,
    sintax_cutoff: float,
    filter_route: str,
    beta_tree_path: str | None,
    rarefaction_depth: int,
    rarefaction_seed: int,
    threads: int,
    command_timeout: float | None,
    usearch_path: str | None,
    vsearch_path: str | None,
) -> None:
    """Run the integrated raw FASTQ pipeline."""

    try:
        click.echo("[CLI] Starting raw FASTQ pipeline.")
        click.echo(f"[CLI] Metadata: {metadata_path}")
        click.echo(f"[CLI] Sequence directory: {seq_dir}")
        click.echo(f"[CLI] Output root: {output_root}")
        click.echo(f"[CLI] Feature method: {feature_method}")
        click.echo(f"[CLI] Merge backend: {merge_backend}")
        click.echo(f"[CLI] OTU table method: {otutab_method}")
        click.echo(f"[CLI] Annotation database: {annotation_database}")
        click.echo(f"[CLI] Filter route: {filter_route}")
        click.echo(f"[CLI] Rarefaction depth: {rarefaction_depth}")
        click.echo(f"[CLI] Rarefaction seed: {rarefaction_seed}")

        outputs = run_raw_amplicon_pipeline(
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
            merge_backend=merge_backend,
            beta_tree_path=beta_tree_path,
            rarefaction_depth=rarefaction_depth,
            rarefaction_seed=rarefaction_seed,
            threads=threads,
            command_timeout=command_timeout,
            read1_suffix=read1_suffix,
            read2_suffix=read2_suffix,
            usearch_path=usearch_path,
            vsearch_path=vsearch_path,
        )
    except (CommandExecutionError, FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] Raw FASTQ pipeline completed successfully.")
    click.echo(f"[CLI] Raw otutab: {outputs['raw_otutab']}")
    click.echo(f"[CLI] Raw sintax: {outputs['raw_sintax']}")
    click.echo(f"[CLI] Final otutab: {outputs['final_outputs']['feature_table']}")
    click.echo(f"[CLI] Final sintax: {outputs['final_outputs']['taxonomy']}")
    click.echo(f"[CLI] Parsed taxonomy: {outputs['analysis_outputs']['taxonomy_table']}")
    click.echo(f"[CLI] Rarefied OTU table: {outputs['analysis_outputs']['rarefied_otutab']}")
    click.echo(f"[CLI] Alpha diversity: {outputs['analysis_outputs']['alpha_diversity']}")
    click.echo(f"[CLI] Alpha rarefaction: {outputs['analysis_outputs']['alpha_rarefaction']}")
    click.echo(f"[CLI] Beta diversity directory: {outputs['analysis_outputs']['beta_dir']}")
    click.echo(
        f"[CLI] Taxonomy summary directory: "
        f"{outputs['analysis_outputs']['taxonomy_summary_dir']}"
    )
    click.echo(f"[CLI] Run summary: {outputs['summary_path']}")
    if outputs.get("provenance"):
        click.echo(f"[CLI] Provenance JSON: {outputs['provenance'].get('json')}")
        click.echo(f"[CLI] Provenance Markdown: {outputs['provenance'].get('markdown')}")


@cli.command("run-pipeline-config")
@click.option(
    "--params",
    "params_path",
    default="pipeline_params.yaml",
    show_default=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="YAML parameter file used to run the integrated raw FASTQ pipeline.",
)
@click.option(
    "--check-only",
    is_flag=True,
    help="Validate params and inputs, then stop before running the pipeline.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Alias for --check-only.",
)
def run_pipeline_config(params_path: str, check_only: bool, dry_run: bool) -> None:
    """Run the integrated raw FASTQ pipeline from a YAML params file."""

    try:
        if check_only or dry_run:
            report = _inspect_pipeline_config(params_path)
            _echo_pipeline_check_report(report)
            if report["status"] != "passed":
                errors = report["errors"]
                assert isinstance(errors, list)
                raise click.ClickException("\n".join(str(error) for error in errors))
            click.echo("[CLI] Check-only mode completed without blocking issues.")
            return

        pipeline_params = _load_pipeline_params(params_path)

        click.echo("[CLI] Starting raw FASTQ pipeline from params file.")
        click.echo(f"[CLI] Params file: {os.path.abspath(params_path)}")
        click.echo(f"[CLI] Metadata: {pipeline_params['metadata_path']}")
        click.echo(f"[CLI] Sequence directory: {pipeline_params['seq_dir']}")
        click.echo(f"[CLI] Output root: {pipeline_params['output_root']}")
        click.echo(f"[CLI] Feature method: {pipeline_params['feature_method']}")
        click.echo(f"[CLI] Merge backend: {pipeline_params['merge_backend']}")
        click.echo(f"[CLI] OTU table method: {pipeline_params['otutab_method']}")
        click.echo(
            f"[CLI] Annotation database: {pipeline_params['annotation_database']}"
        )
        click.echo(f"[CLI] Filter route: {pipeline_params['filter_route']}")
        click.echo(f"[CLI] Rarefaction depth: {pipeline_params['rarefaction_depth']}")
        click.echo(f"[CLI] Rarefaction seed: {pipeline_params['rarefaction_seed']}")

        outputs = run_raw_amplicon_pipeline(
            **pipeline_params,
            params_source=os.path.abspath(params_path),
        )
    except (CommandExecutionError, FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] Raw FASTQ pipeline completed successfully.")
    click.echo(f"[CLI] Raw otutab: {outputs['raw_otutab']}")
    click.echo(f"[CLI] Raw sintax: {outputs['raw_sintax']}")
    click.echo(f"[CLI] Final otutab: {outputs['final_outputs']['feature_table']}")
    click.echo(f"[CLI] Final sintax: {outputs['final_outputs']['taxonomy']}")
    click.echo(f"[CLI] Parsed taxonomy: {outputs['analysis_outputs']['taxonomy_table']}")
    click.echo(f"[CLI] Rarefied OTU table: {outputs['analysis_outputs']['rarefied_otutab']}")
    click.echo(f"[CLI] Alpha diversity: {outputs['analysis_outputs']['alpha_diversity']}")
    click.echo(f"[CLI] Alpha rarefaction: {outputs['analysis_outputs']['alpha_rarefaction']}")
    click.echo(f"[CLI] Beta diversity directory: {outputs['analysis_outputs']['beta_dir']}")
    click.echo(
        f"[CLI] Taxonomy summary directory: "
        f"{outputs['analysis_outputs']['taxonomy_summary_dir']}"
    )
    click.echo(f"[CLI] Run summary: {outputs['summary_path']}")
    if outputs.get("provenance"):
        click.echo(f"[CLI] Provenance JSON: {outputs['provenance'].get('json')}")
        click.echo(f"[CLI] Provenance Markdown: {outputs['provenance'].get('markdown')}")


@cli.command("vsearch-otu")
@click.option(
    "--input",
    "input_fasta",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Input FASTA file used for VSEARCH OTU clustering.",
)
@click.option(
    "--output",
    "output_dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Output directory for clustering results.",
)
@click.option(
    "--threads",
    default=None,
    type=click.IntRange(min=1),
    help="Optional CPU thread count passed to VSEARCH. If omitted, VSEARCH default is used.",
)
@click.option(
    "--identity",
    type=float,
    default=None,
    help="OTU clustering identity threshold. If omitted, config.yaml is used.",
)
@click.option(
    "--minsize",
    type=click.IntRange(min=1),
    default=None,
    help="Minimum abundance threshold for input unique sequences.",
)
@click.option(
    "--config",
    "config_path",
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Path to the YAML config file.",
)
@click.option(
    "--vsearch-path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    help="Optional explicit path to the VSEARCH executable.",
)
@click.option(
    "--otu-fasta",
    "otu_fasta_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional output path for the final non-chimeric OTU FASTA file.",
)
def vsearch_otu(
    input_fasta: str,
    output_dir: str,
    threads: int,
    identity: float | None,
    minsize: int | None,
    config_path: str,
    vsearch_path: str | None,
    otu_fasta_path: str | None,
) -> None:
    """Run the VSEARCH 97% OTU clustering workflow."""

    try:
        defaults = load_vsearch_otu_defaults(config_path)
        effective_identity = identity if identity is not None else defaults["identity"]
        effective_minsize = minsize if minsize is not None else defaults["minsize"]

        click.echo("[CLI] Starting VSEARCH OTU clustering.")
        click.echo(f"[CLI] Config file: {config_path}")
        click.echo(f"[CLI] Effective identity threshold: {effective_identity}")
        click.echo(f"[CLI] Effective minimum abundance threshold: {effective_minsize}")

        outputs = run_vsearch_otu_clustering(
            input_fasta=input_fasta,
            output_dir=output_dir,
            threads=threads,
            identity=identity,
            minsize=minsize,
            config_path=config_path,
            vsearch_path=vsearch_path,
            otu_fasta_path=otu_fasta_path,
        )
    except (CommandExecutionError, FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] VSEARCH OTU clustering completed successfully.")
    click.echo(f"[CLI] Final OTU FASTA: {outputs['otu_fasta']}")
    click.echo(f"[CLI] Non-chimeric OTUs: {outputs['nonchimeric_otus']}")
    click.echo(f"[CLI] OTU table: {outputs['otu_table']}")


@cli.command("vsearch-uchime-ref")
@click.option(
    "--input",
    "input_fasta",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Input FASTA file to be filtered with VSEARCH uchime_ref.",
)
@click.option(
    "--output",
    "output_dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Output directory for uchime_ref results.",
)
@click.option(
    "--threads",
    default=None,
    type=click.IntRange(min=1),
    help="Optional CPU thread count passed to VSEARCH. If omitted, VSEARCH default is used.",
)
@click.option(
    "--reference-db",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Reference FASTA database used by uchime_ref.",
)
@click.option(
    "--chimera-mode",
    default=None,
    type=click.Choice(["ref", "none"], case_sensitive=False),
    help="Chimera handling mode: ref runs uchime_ref, none copies input directly.",
)
@click.option(
    "--config",
    "config_path",
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Path to the YAML config file.",
)
@click.option(
    "--vsearch-path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    help="Optional explicit path to the VSEARCH executable.",
)
@click.option(
    "--result-fasta",
    "output_fasta_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional output path for the final result FASTA file.",
)
@click.option(
    "--order-template-fasta",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Optional FASTA file whose header order should be used to reorder the output.",
)
def vsearch_uchime_ref(
    input_fasta: str,
    output_dir: str,
    threads: int,
    reference_db: str | None,
    chimera_mode: str | None,
    config_path: str,
    vsearch_path: str | None,
    output_fasta_path: str | None,
    order_template_fasta: str | None,
) -> None:
    """Run VSEARCH uchime_ref or optionally bypass chimera filtering."""

    try:
        defaults = load_vsearch_uchime_ref_defaults(config_path)
        effective_reference_db = (
            reference_db if reference_db is not None else defaults["reference_db"]
        )
        effective_chimera_mode = (
            chimera_mode if chimera_mode is not None else defaults["chimera_mode"]
        )

        click.echo("[CLI] Starting VSEARCH uchime_ref workflow.")
        click.echo(f"[CLI] Config file: {config_path}")
        click.echo(f"[CLI] Effective reference database: {effective_reference_db}")
        click.echo(f"[CLI] Effective chimera mode: {effective_chimera_mode}")

        outputs = run_vsearch_uchime_ref(
            input_fasta=input_fasta,
            output_dir=output_dir,
            threads=threads,
            reference_db=reference_db,
            chimera_mode=chimera_mode,
            order_template_fasta=order_template_fasta,
            config_path=config_path,
            vsearch_path=vsearch_path,
            output_fasta_path=output_fasta_path,
        )
    except (CommandExecutionError, FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] VSEARCH uchime_ref workflow completed successfully.")
    click.echo(f"[CLI] Result FASTA: {outputs['result_fasta']}")
    if outputs["uchime_report"] is not None:
        click.echo(f"[CLI] UCHIME report: {outputs['uchime_report']}")


@cli.command("vsearch-sintax")
@click.option(
    "--input",
    "input_fasta",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Input FASTA file containing OTU or ASV representative sequences.",
)
@click.option(
    "--output",
    "output_dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Output directory for VSEARCH sintax results.",
)
@click.option(
    "--threads",
    default=None,
    type=click.IntRange(min=1),
    help="Optional CPU thread count passed to VSEARCH. If omitted, VSEARCH default is used.",
)
@click.option(
    "--database",
    default=None,
    type=str,
    help="Registered database name, alias, or FASTA path used for taxonomic annotation.",
)
@click.option(
    "--sintax-cutoff",
    type=float,
    default=None,
    help="Confidence cutoff passed to VSEARCH sintax. If omitted, config.yaml is used.",
)
@click.option(
    "--wordlength",
    default=None,
    type=click.IntRange(min=3, max=15),
    help="Optional VSEARCH sintax word length.",
)
@click.option(
    "--strand",
    default=None,
    type=click.Choice(["plus", "both"], case_sensitive=False),
    help="Optional strand mode passed to VSEARCH sintax.",
)
@click.option(
    "--dbmask",
    default=None,
    type=click.Choice(["none", "dust", "soft"], case_sensitive=False),
    help="Optional database masking mode passed to VSEARCH sintax.",
)
@click.option(
    "--randseed",
    default=None,
    type=click.IntRange(min=1),
    help="Optional random seed for VSEARCH versions that support it.",
)
@click.option(
    "--sintax-random",
    is_flag=True,
    help="Pass --sintax_random when supported by the selected VSEARCH executable.",
)
@click.option(
    "--config",
    "config_path",
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Path to the YAML config file.",
)
@click.option(
    "--vsearch-path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    help="Optional explicit path to the VSEARCH executable.",
)
@click.option(
    "--annotation-path",
    "output_annotation_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional explicit output path for the final sintax annotation table.",
)
def vsearch_sintax(
    input_fasta: str,
    output_dir: str,
    threads: int | None,
    database: str | None,
    sintax_cutoff: float | None,
    wordlength: int | None,
    strand: str | None,
    dbmask: str | None,
    randseed: int | None,
    sintax_random: bool,
    config_path: str,
    vsearch_path: str | None,
    output_annotation_path: str | None,
) -> None:
    """Run taxonomic annotation with VSEARCH sintax."""

    try:
        defaults = load_vsearch_sintax_defaults(config_path)
        effective_database = database if database is not None else defaults["database"]
        effective_sintax_cutoff = (
            sintax_cutoff
            if sintax_cutoff is not None
            else defaults["sintax_cutoff"]
        )

        click.echo("[CLI] Starting VSEARCH sintax workflow.")
        click.echo(f"[CLI] Config file: {config_path}")
        click.echo(f"[CLI] Effective database: {effective_database}")
        click.echo(f"[CLI] Effective sintax cutoff: {effective_sintax_cutoff}")
        click.echo(
            "[CLI] Effective threads: "
            f"{threads if threads is not None else 'vsearch default'}"
        )

        outputs = run_vsearch_sintax(
            input_fasta=input_fasta,
            output_dir=output_dir,
            threads=threads,
            database=database,
            sintax_cutoff=sintax_cutoff,
            wordlength=wordlength,
            strand=strand,
            dbmask=dbmask,
            randseed=randseed,
            sintax_random=sintax_random,
            config_path=config_path,
            vsearch_path=vsearch_path,
            output_annotation_path=output_annotation_path,
        )
    except (CommandExecutionError, FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] VSEARCH sintax workflow completed successfully.")
    click.echo(f"[CLI] Database: {outputs['database']}")
    click.echo(f"[CLI] Annotation table: {outputs['sintax_table']}")


@cli.command("alpha-diversity")
@click.option(
    "--input",
    "input_table",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Input OTU table with OTU IDs as rows and sample IDs as columns.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Output path for the alpha diversity table.",
)
@click.option(
    "--rarefaction-output",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional output path for the rarefaction curve table.",
)
@click.option(
    "--depth",
    "depths",
    multiple=True,
    type=click.IntRange(min=1),
    help="Repeat this option to calculate rarefaction curves at one or more depths.",
)
def alpha_diversity(
    input_table: str,
    output_path: str,
    rarefaction_output: str | None,
    depths: tuple[int, ...],
) -> None:
    """Calculate alpha diversity metrics and optional rarefaction curves."""

    try:
        if rarefaction_output is not None and not depths:
            raise ValueError("rarefaction-output requires at least one --depth value.")

        otutab = _read_table(input_table)
        alpha_path = _write_table(calculate_alpha_diversity(otutab), output_path)

        rarefaction_path = None
        if depths:
            rarefaction_result = calculate_rarefaction_curve(otutab, list(depths))
            target_path = rarefaction_output or os.path.join(
                os.path.dirname(alpha_path),
                "alpha_rarefaction.tsv",
            )
            rarefaction_path = _write_table(
                rarefaction_result,
                target_path,
                include_index=False,
            )
    except (FileNotFoundError, ImportError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] Alpha diversity workflow completed successfully.")
    click.echo(f"[CLI] Alpha diversity table: {alpha_path}")
    if rarefaction_path is not None:
        click.echo(f"[CLI] Rarefaction curve table: {rarefaction_path}")


@cli.command("feature-filter")
@click.option(
    "--input",
    "input_table",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Input OTU table with OTU IDs as rows and sample IDs as columns.",
)
@click.option(
    "--metadata",
    "metadata_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Metadata table used to group samples.",
)
@click.option(
    "--group-col",
    required=True,
    type=str,
    help="Metadata column used to group samples.",
)
@click.option(
    "--threshold",
    default=0.001,
    show_default=True,
    type=float,
    help="Minimum mean relative abundance as a fraction, so 0.001 means 0.1%.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Output path for the filtered group-abundance table.",
)
def feature_filter(
    input_table: str,
    metadata_path: str,
    group_col: str,
    threshold: float,
    output_path: str,
) -> None:
    """Calculate group mean relative abundance and filter low-abundance features."""

    try:
        otutab = _read_table(input_table)
        metadata = _read_metadata_table(metadata_path)
        result = calculate_group_abundance(
            otutab=otutab,
            metadata=metadata,
            group_col=group_col,
            threshold=threshold,
        )
        resolved_output_path = _write_table(result, output_path)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] Feature filter workflow completed successfully.")
    click.echo(f"[CLI] Group abundance table: {resolved_output_path}")


@cli.command("beta-diversity")
@click.option(
    "--input",
    "input_table",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Input OTU table with OTU IDs as rows and sample IDs as columns.",
)
@click.option(
    "--output",
    "output_dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Output directory for one or more beta diversity matrices.",
)
@click.option(
    "--metric",
    "metrics",
    multiple=True,
    required=True,
    type=str,
    help=(
        "Repeat this option to calculate multiple beta diversity metrics. "
        "Supported values: "
        + ", ".join(SUPPORTED_BETA_METRICS)
    ),
)
@click.option(
    "--tree",
    "tree_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Optional rooted tree required for UniFrac metrics.",
)
def beta_diversity(
    input_table: str,
    output_dir: str,
    metrics: tuple[str, ...],
    tree_path: str | None,
) -> None:
    """Calculate one or more beta diversity distance matrices."""

    try:
        otutab = _read_table(input_table)
        tree = None if tree_path is None else _load_tree(tree_path)
        written_paths: list[str] = []
        for metric in dict.fromkeys(
            normalize_beta_metric_name(metric) for metric in metrics
        ):
            result = calculate_beta_distance(otutab, metric, tree=tree)
            written_paths.append(
                _write_table(result, os.path.join(output_dir, f"{metric}.tsv"))
            )
    except (FileNotFoundError, ImportError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] Beta diversity workflow completed successfully.")
    for written_path in written_paths:
        click.echo(f"[CLI] Distance matrix: {written_path}")


@cli.command("phylogenetic-tree")
@click.option(
    "--input",
    "input_fasta",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Representative OTU/ASV FASTA file used to generate the tree.",
)
@click.option(
    "--output",
    "output_tree_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Output Newick tree path.",
)
@click.option(
    "--linkage",
    default="max",
    show_default=True,
    type=click.Choice(["max", "min", "avg"], case_sensitive=False),
    help="Agglomerative linkage method. USEARCH cluster_agg defaults to max.",
)
def phylogenetic_tree(
    input_fasta: str,
    output_tree_path: str,
    linkage: str,
) -> None:
    """Generate a rooted Newick tree from representative sequences."""

    try:
        outputs = run_phylogenetic_tree_generation(
            input_fasta=input_fasta,
            output_tree_path=output_tree_path,
            linkage=linkage.lower(),
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] Phylogenetic tree workflow completed successfully.")
    click.echo(f"[CLI] Tree: {outputs['tree_path']}")
    click.echo(f"[CLI] Records: {outputs['record_count']}")
    click.echo(f"[CLI] Linkage: {outputs['linkage']}")


@cli.command("taxonomy-summary")
@click.option(
    "--sintax",
    "sintax_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Input sintax annotation file.",
)
@click.option(
    "--otutab",
    "input_table",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Optional OTU table used to generate rank-level abundance summaries.",
)
@click.option(
    "--rank",
    "ranks",
    multiple=True,
    type=str,
    help="Repeat this option to summarize one or more taxonomy ranks.",
)
@click.option(
    "--output",
    "output_dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Output directory for the parsed taxonomy table and optional summaries.",
)
def taxonomy_summary(
    sintax_path: str,
    input_table: str | None,
    ranks: tuple[str, ...],
    output_dir: str,
) -> None:
    """Parse sintax output and optionally summarize abundance by taxonomy rank."""

    try:
        if ranks and input_table is None:
            raise ValueError("--rank requires --otutab.")

        taxonomy = parse_sintax_to_dataframe(sintax_path)
        taxonomy_path = _write_table(
            taxonomy,
            os.path.join(output_dir, "taxonomy.tsv"),
            include_index=False,
        )

        summary_paths: list[str] = []
        if input_table is not None:
            otutab = _read_table(input_table)
            resolved_ranks = (
                [_resolve_taxonomy_rank(rank) for rank in ranks]
                if ranks
                else list(DEFAULT_TAXONOMY_RANKS)
            )
            summary_dir = os.path.join(output_dir, "taxonomy_summary")
            for rank in resolved_ranks:
                result = summarize_taxa_abundance(otutab, taxonomy, rank)
                summary_paths.append(
                    _write_table(result, os.path.join(summary_dir, f"{rank.lower()}.tsv"))
                )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] Taxonomy summary workflow completed successfully.")
    click.echo(f"[CLI] Parsed taxonomy table: {taxonomy_path}")
    for summary_path in summary_paths:
        click.echo(f"[CLI] Taxonomy summary table: {summary_path}")


@cli.command("visualization-suite")
@click.option(
    "--final-dir",
    default=os.path.join("work", "06_final"),
    show_default=True,
    type=click.Path(exists=True, file_okay=False, readable=True, path_type=str),
    help="Completed pipeline final directory containing alpha, beta, and taxonomy_summary outputs.",
)
@click.option(
    "--metadata",
    "metadata_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Optional metadata table. Defaults to <work_root>/00_input/metadata.txt when present.",
)
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Plot output root. Defaults to <final-dir>/plots.",
)
@click.option(
    "--format",
    "output_format",
    default="html",
    show_default=True,
    type=click.Choice(["html", "png", "pdf", "svg", "all"], case_sensitive=False),
    help="Visualization output format. Static png/pdf/svg exports require kaleido.",
)
@click.option("--sample-id-col", default="SampleID", show_default=True, help="Metadata sample ID column.")
@click.option("--group-col", default="Group", show_default=True, help="Metadata group column.")
@click.option(
    "--color-palette",
    default=None,
    help="Optional comma-separated colors or Group:#hex pairs, for example WT:#4E79A7,KO:#E15759.",
)
@click.option("--beta-metric", "beta_metrics", multiple=True, help="Repeat to plot selected beta metrics.")
@click.option(
    "--taxonomy-level",
    "taxonomy_levels",
    multiple=True,
    type=click.Choice(
        ["kingdom", "phylum", "class", "order", "family", "genus", "species"],
        case_sensitive=False,
    ),
    help="Repeat to plot selected taxonomy levels.",
)
@click.option("--skip-cpcoa", is_flag=True, help="Skip constrained beta PCoA plots.")
@click.option("--skip-beta-stats", is_flag=True, help="Skip beta heatmaps and group tests.")
@click.option("--skip-taxonomy-heatmaps", is_flag=True, help="Skip taxonomy heatmaps.")
@click.option("--skip-taxonomy-stacked-bars", is_flag=True, help="Skip taxonomy stacked bar charts.")
def visualization_suite(
    final_dir: str,
    metadata_path: str | None,
    output_dir: str | None,
    output_format: str,
    sample_id_col: str,
    group_col: str,
    color_palette: str | None,
    beta_metrics: tuple[str, ...],
    taxonomy_levels: tuple[str, ...],
    skip_cpcoa: bool,
    skip_beta_stats: bool,
    skip_taxonomy_heatmaps: bool,
    skip_taxonomy_stacked_bars: bool,
) -> None:
    """Generate publication-ready visualization charts for a completed pipeline run."""

    try:
        from src.core.viz_pipeline import run_visualization_suite

        result = run_visualization_suite(
            final_dir=final_dir,
            metadata_path=metadata_path,
            output_dir=output_dir,
            output_format=output_format,
            sample_id_col=sample_id_col,
            group_col=group_col,
            color_palette=color_palette,
            beta_metrics=list(beta_metrics) or None,
            taxonomy_levels=list(taxonomy_levels) or None,
            include_cpcoa=not skip_cpcoa,
            include_beta_stats=not skip_beta_stats,
            include_taxonomy_heatmaps=not skip_taxonomy_heatmaps,
            include_taxonomy_stacked_bars=not skip_taxonomy_stacked_bars,
        )
    except ImportError as exc:
        raise click.ClickException(
            "Visualization dependencies are not available. Install plotly and scipy; "
            "install kaleido as well for png/pdf/svg output. "
            f"Original error: {exc}"
        ) from exc
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    generated_files = result.get("generated_files", [])
    skipped_static = result.get("skipped_static_exports", [])
    click.echo("[CLI] Visualization suite completed successfully.")
    click.echo(f"[CLI] Final directory: {result.get('final_dir')}")
    click.echo(f"[CLI] Metadata: {result.get('metadata') or '(inferred from sample IDs)'}")
    click.echo(f"[CLI] Output root: {result.get('output_dir')}")
    click.echo(f"[CLI] Output format: {result.get('output_format')}")
    if result.get("color_palette"):
        click.echo(f"[CLI] Color palette: {result.get('color_palette')}")
    if isinstance(result.get("output_subdirs"), dict):
        for key, path in result["output_subdirs"].items():
            click.echo(f"[CLI] Plot subdirectory ({key}): {path}")
    click.echo(f"[CLI] Generated files: {len(generated_files)}")
    if skipped_static:
        click.echo(f"[CLI] Skipped static exports: {len(skipped_static)}")


@cli.command("differential-abundance")
@click.option(
    "--otutab",
    "otutab_path",
    default=os.path.join("work", "06_final", "otutab.txt"),
    show_default=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Final OTU/ASV table with features as rows and samples as columns.",
)
@click.option(
    "--metadata",
    "metadata_path",
    default=os.path.join("work", "00_input", "metadata.txt"),
    show_default=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Metadata table containing sample IDs and the grouping column.",
)
@click.option(
    "--output-dir",
    default=os.path.join("work", "06_final", "statistics", "differential"),
    show_default=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Differential output root. Results, volcano plots, and heatmaps are written to subdirectories.",
)
@click.option("--group-col", default="Group", show_default=True, help="Metadata grouping column.")
@click.option("--sample-id-col", default="SampleID", show_default=True, help="Metadata sample ID column.")
@click.option(
    "--compare",
    "comparisons",
    multiple=True,
    help="Pairwise comparison in CASE:CONTROL or CASE_vs_CONTROL format. Repeat for multiple comparisons.",
)
@click.option(
    "--reference-group",
    default=None,
    help="Generate all non-reference groups versus this control/reference group.",
)
@click.option(
    "--comparison-plan",
    "comparison_plan_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Existing comparison_plan.tsv. Mark Include=yes and add --run-confirmed-plan to run it.",
)
@click.option(
    "--run-confirmed-plan",
    is_flag=True,
    help="Run comparisons marked Include=yes in --comparison-plan.",
)
@click.option(
    "--method",
    default="wilcox",
    show_default=True,
    type=click.Choice(["wilcox", "t.test"], case_sensitive=False),
    help="Pairwise statistical test. edgeR is not bundled in the Python distribution.",
)
@click.option(
    "--min-mean-relative-abundance",
    default=0.001,
    show_default=True,
    type=float,
    help="Minimum mean relative abundance percentage required for a feature to be tested.",
)
@click.option("--pvalue", default=0.05, show_default=True, type=float, help="P-value threshold.")
@click.option("--fdr", default=0.2, show_default=True, type=float, help="FDR threshold.")
@click.option(
    "--log2fc-threshold",
    default=0.0,
    show_default=True,
    type=float,
    help="Minimum absolute log2 fold change required for Enriched/Depleted labels.",
)
@click.option(
    "--taxonomy",
    "taxonomy_path",
    default=os.path.join("work", "06_final", "taxonomy.tsv"),
    show_default=True,
    type=click.Path(dir_okay=False, readable=True, path_type=str),
    help="Optional taxonomy table used for plot hover labels and result annotation.",
)
@click.option(
    "--format",
    "output_format",
    default="html",
    show_default=True,
    type=click.Choice(["html", "png", "pdf", "svg", "all"], case_sensitive=False),
    help="Plot output format. Static png/pdf/svg exports require kaleido.",
)
@click.option(
    "--min-samples-per-group",
    default=2,
    show_default=True,
    type=int,
    help="Minimum aligned sample count required in each group.",
)
@click.option(
    "--top-n-heatmap",
    default=30,
    show_default=True,
    type=int,
    help="Maximum number of differential features shown in each heatmap.",
)
def differential_abundance(
    otutab_path: str,
    metadata_path: str,
    output_dir: str,
    group_col: str,
    sample_id_col: str,
    comparisons: tuple[str, ...],
    reference_group: str | None,
    comparison_plan_path: str | None,
    run_confirmed_plan: bool,
    method: str,
    min_mean_relative_abundance: float,
    pvalue: float,
    fdr: float,
    log2fc_threshold: float,
    taxonomy_path: str | None,
    output_format: str,
    min_samples_per_group: int,
    top_n_heatmap: int,
) -> None:
    """Run pairwise differential abundance and generate volcano/heatmap plots."""

    try:
        result = run_taxonomy_differential_abundance(
            otutab_path=otutab_path,
            metadata_path=metadata_path,
            output_dir=output_dir,
            group_col=group_col,
            sample_id_col=sample_id_col,
            comparisons=list(comparisons) or None,
            reference_group=reference_group,
            comparison_plan_path=comparison_plan_path,
            run_confirmed_plan=run_confirmed_plan,
            method=method,
            min_mean_relative_abundance=min_mean_relative_abundance,
            pvalue=pvalue,
            fdr=fdr,
            log2fc_threshold=log2fc_threshold,
            taxonomy_path=taxonomy_path,
            output_format=output_format,
            min_samples_per_group=min_samples_per_group,
            top_n_heatmap=top_n_heatmap,
        )
    except ImportError as exc:
        raise click.ClickException(
            "Differential plotting dependencies are not available. Install plotly and scipy; "
            "install kaleido as well for png/pdf/svg output. "
            f"Original error: {exc}"
        ) from exc
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    generated_files = result.get("generated_files", [])
    skipped_static = result.get("skipped_static_exports", [])
    click.echo(f"[CLI] Differential abundance status: {result.get('status')}")
    click.echo(f"[CLI] Output root: {result.get('output_dir') or output_dir}")
    click.echo(f"[CLI] Comparison plan: {result.get('comparison_plan')}")
    if not result.get("analysis_ran"):
        click.echo(f"[CLI] {result.get('message')}")
        click.echo("[CLI] No statistics or plots were generated yet.")
        return

    click.echo(f"[CLI] Method: {result.get('method')}")
    for comparison, details in result.get("comparisons", {}).items():
        click.echo(
            "[CLI] Comparison "
            f"{comparison}: features tested={details.get('features_tested')}, "
            f"significant={details.get('significant_features')}"
        )
        click.echo(f"[CLI] Result table: {details.get('result_table')}")
        click.echo(f"[CLI] Volcano directory: {details.get('volcano', {}).get('output_dir')}")
        click.echo(f"[CLI] Heatmap directory: {details.get('heatmap', {}).get('output_dir')}")
    click.echo(f"[CLI] Generated files: {len(generated_files)}")
    if skipped_static:
        click.echo(f"[CLI] Skipped static exports: {len(skipped_static)}")


cli.add_command(differential_abundance, "taxonomy-stats")


@cli.command("otutab-filter")
@click.option(
    "--input",
    "input_table",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Input feature table, typically result/raw/otutab.txt.",
)
@click.option(
    "--taxonomy",
    "taxonomy_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Input sintax taxonomy table, typically result/raw/otus.sintax.",
)
@click.option(
    "--representatives",
    "representative_fasta",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Input representative FASTA, typically result/raw/otus.fa.",
)
@click.option(
    "--output",
    "output_dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Output directory for filtered files.",
)
@click.option(
    "--route",
    required=True,
    type=click.Choice(["16s", "its", "none"], case_sensitive=False),
    help="Filtering route: 16s removes non-Bacteria/Archaea plus chloroplast/mitochondria; its keeps Fungi; none copies files directly.",
)
@click.option(
    "--usearch-path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    help="Deprecated; representative FASTA extraction is handled internally.",
)
@click.option(
    "--table-path",
    "output_table_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional explicit output path for the filtered feature table.",
)
@click.option(
    "--fasta-path",
    "output_fasta_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional explicit output path for the filtered representative FASTA.",
)
@click.option(
    "--taxonomy-path",
    "output_taxonomy_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional explicit output path for the filtered sintax file.",
)
@click.option(
    "--stat-path",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional explicit output path for the filtering statistics table.",
)
@click.option(
    "--discard-path",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional explicit output path for discarded taxonomy rows.",
)
@click.option(
    "--id-path",
    "output_id_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional explicit output path for the selected feature ID list.",
)
def otutab_filter(
    input_table: str,
    taxonomy_path: str,
    representative_fasta: str,
    output_dir: str,
    route: str,
    usearch_path: str | None,
    output_table_path: str | None,
    output_fasta_path: str | None,
    output_taxonomy_path: str | None,
    stat_path: str | None,
    discard_path: str | None,
    output_id_path: str | None,
) -> None:
    """Filter feature tables by taxonomy and extract matching representatives."""

    try:
        click.echo("[CLI] Starting OTU/feature taxonomy filtering workflow.")
        click.echo(f"[CLI] Input feature table: {input_table}")
        click.echo(f"[CLI] Input taxonomy: {taxonomy_path}")
        click.echo(f"[CLI] Input representative FASTA: {representative_fasta}")
        click.echo(f"[CLI] Route: {route}")

        outputs = run_otutab_filter(
            input_table=input_table,
            taxonomy_path=taxonomy_path,
            representative_fasta=representative_fasta,
            output_dir=output_dir,
            route=route,
            usearch_path=usearch_path,
            output_table_path=output_table_path,
            output_fasta_path=output_fasta_path,
            output_taxonomy_path=output_taxonomy_path,
            output_stat_path=stat_path,
            discard_path=discard_path,
            output_id_path=output_id_path,
        )
    except (CommandExecutionError, FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] OTU/feature taxonomy filtering workflow completed successfully.")
    click.echo(f"[CLI] Route: {outputs['route']}")
    click.echo(f"[CLI] Feature table: {outputs['feature_table']}")
    click.echo(f"[CLI] Representative FASTA: {outputs['representative_fasta']}")
    click.echo(f"[CLI] Taxonomy: {outputs['taxonomy']}")


@cli.command("otutab-rare")
@click.option(
    "--input",
    "input_table",
    default="result/otutab.txt",
    show_default=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Input feature table to rarefy.",
)
@click.option(
    "--depth",
    default=0,
    show_default=True,
    type=click.IntRange(min=0),
    help="Rarefaction depth. Use 0 to select the minimum sample depth automatically.",
)
@click.option(
    "--seed",
    default=1,
    show_default=True,
    type=int,
    help="Random seed used for rarefaction.",
)
@click.option(
    "--normalize",
    "normalize_path",
    default="result/otutab_rare.txt",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Output path for the rarefied OTU table.",
)
@click.option(
    "--output",
    "output_path",
    default="result/alpha/vegan.txt",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Output path for alpha diversity metrics.",
)
@click.option(
    "--stats-path",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional output path for Python-generated OTU table statistics.",
)
@click.option(
    "--usearch-path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    help="Deprecated; OTU table statistics are generated internally.",
)
def otutab_rare(
    input_table: str,
    depth: int,
    seed: int,
    normalize_path: str,
    output_path: str,
    stats_path: str | None,
    usearch_path: str | None,
) -> None:
    """Rarefy an OTU table, compute alpha diversity, and write OTU table stats."""

    try:
        click.echo("[CLI] Starting OTU table rarefaction workflow.")
        click.echo(f"[CLI] Input feature table: {input_table}")
        click.echo(f"[CLI] Rarefaction depth: {depth}")
        click.echo(f"[CLI] Random seed: {seed}")

        outputs = run_otutab_rare(
            input_table=input_table,
            depth=depth,
            seed=seed,
            normalize_path=normalize_path,
            output_path=output_path,
            stats_path=stats_path,
            usearch_path=usearch_path,
        )
    except (CommandExecutionError, FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] OTU table rarefaction workflow completed successfully.")
    click.echo(f"[CLI] Rarefied table: {outputs['normalize']}")
    click.echo(f"[CLI] Alpha diversity: {outputs['alpha']}")
    click.echo(f"[CLI] Discard samples: {outputs['discard']}")
    click.echo(f"[CLI] OTU table stats: {outputs['stats']}")


@cli.command("otutab")
@click.option(
    "--input",
    "input_fasta",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Input FASTA file containing filtered reads or feature candidates.",
)
@click.option(
    "--representatives",
    "representative_fasta",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Representative OTU/ASV FASTA file used as the database.",
)
@click.option(
    "--output",
    "output_dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Output directory for the OTU/feature table.",
)
@click.option(
    "--method",
    default=None,
    type=click.Choice(["usearch", "vsearch"], case_sensitive=False),
    help="Backend used to generate the OTU table.",
)
@click.option(
    "--threads",
    default=1,
    show_default=True,
    type=click.IntRange(min=1),
    help="Number of CPU threads passed to the selected backend.",
)
@click.option(
    "--identity",
    type=float,
    default=None,
    help="Identity threshold used by the VSEARCH backend. Ignored for USEARCH.",
)
@click.option(
    "--config",
    "config_path",
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Path to the YAML config file.",
)
@click.option(
    "--tool-path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    help="Optional explicit path to the selected USEARCH or VSEARCH executable.",
)
@click.option(
    "--table-path",
    "output_table_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional explicit output path for the generated OTU table.",
)
def otutab(
    input_fasta: str,
    representative_fasta: str,
    output_dir: str,
    method: str | None,
    threads: int,
    identity: float | None,
    config_path: str,
    tool_path: str | None,
    output_table_path: str | None,
) -> None:
    """Generate an OTU/feature table using either USEARCH or VSEARCH."""

    try:
        defaults = load_otutab_defaults(config_path)
        effective_method = method if method is not None else defaults["method"]
        effective_identity = identity if identity is not None else defaults["identity"]

        click.echo("[CLI] Starting OTU/feature table generation.")
        click.echo(f"[CLI] Config file: {config_path}")
        click.echo(f"[CLI] Effective method: {effective_method}")
        if str(effective_method).lower() == "vsearch":
            click.echo(f"[CLI] Effective identity threshold: {effective_identity}")

        outputs = run_otutab_generation(
            input_fasta=input_fasta,
            representative_fasta=representative_fasta,
            output_dir=output_dir,
            method=effective_method,
            threads=threads,
            identity=identity,
            config_path=config_path,
            tool_path=tool_path,
            output_table_path=output_table_path,
        )
    except (CommandExecutionError, FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] OTU/feature table generation completed successfully.")
    click.echo(f"[CLI] OTU table: {outputs['otutab']}")


@cli.command("usearch-otu")
@click.option(
    "--input",
    "input_fasta",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Input FASTA file used for USEARCH cluster_otus.",
)
@click.option(
    "--output",
    "output_dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Output directory for USEARCH OTU results.",
)
@click.option(
    "--threads",
    default=1,
    show_default=True,
    type=click.IntRange(min=1),
    help="Number of CPU threads passed to USEARCH otutab.",
)
@click.option(
    "--minsize",
    type=click.IntRange(min=1),
    default=None,
    help="Minimum abundance threshold passed to USEARCH cluster_otus.",
)
@click.option(
    "--config",
    "config_path",
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Path to the YAML config file.",
)
@click.option(
    "--usearch-path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    help="Optional explicit path to the USEARCH executable.",
)
@click.option(
    "--otu-fasta",
    "otu_fasta_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional output path for the final OTU FASTA file.",
)
def usearch_otu(
    input_fasta: str,
    output_dir: str,
    threads: int,
    minsize: int | None,
    config_path: str,
    usearch_path: str | None,
    otu_fasta_path: str | None,
) -> None:
    """Run the USEARCH 97% OTU clustering workflow."""

    try:
        defaults = load_usearch_otu_defaults(config_path)
        effective_minsize = minsize if minsize is not None else defaults["minsize"]

        click.echo("[CLI] Starting USEARCH OTU clustering.")
        click.echo(f"[CLI] Config file: {config_path}")
        click.echo(f"[CLI] Effective minimum abundance threshold: {effective_minsize}")

        outputs = run_usearch_otu_clustering(
            input_fasta=input_fasta,
            output_dir=output_dir,
            threads=threads,
            minsize=minsize,
            config_path=config_path,
            usearch_path=usearch_path,
            otu_fasta_path=otu_fasta_path,
        )
    except (CommandExecutionError, FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] USEARCH OTU clustering completed successfully.")
    click.echo(f"[CLI] Final OTU FASTA: {outputs['otu_fasta']}")
    click.echo(f"[CLI] OTU table: {outputs['otu_table']}")


@cli.command("usearch-asv")
@click.option(
    "--input",
    "input_fasta",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=str),
    help="Input FASTA file used for USEARCH UNOISE3 denoising.",
)
@click.option(
    "--output",
    "output_dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Output directory for USEARCH ASV results.",
)
@click.option(
    "--threads",
    default=1,
    show_default=True,
    type=click.IntRange(min=1),
    help="Number of CPU threads passed to USEARCH otutab.",
)
@click.option(
    "--minsize",
    type=click.IntRange(min=1),
    default=None,
    help="Minimum abundance threshold passed to USEARCH unoise3.",
)
@click.option(
    "--config",
    "config_path",
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Path to the YAML config file.",
)
@click.option(
    "--usearch-path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    help="Optional explicit path to the USEARCH executable.",
)
@click.option(
    "--asv-fasta",
    "asv_fasta_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional output path for the final ASV FASTA file.",
)
def usearch_asv(
    input_fasta: str,
    output_dir: str,
    threads: int,
    minsize: int | None,
    config_path: str,
    usearch_path: str | None,
    asv_fasta_path: str | None,
) -> None:
    """Run the USEARCH UNOISE3 ASV denoising workflow."""

    try:
        defaults = load_usearch_asv_defaults(config_path)
        effective_minsize = minsize if minsize is not None else defaults["minsize"]

        click.echo("[CLI] Starting USEARCH ASV denoising.")
        click.echo(f"[CLI] Config file: {config_path}")
        click.echo(f"[CLI] Effective minimum abundance threshold: {effective_minsize}")

        outputs = run_usearch_unoise3_denoising(
            input_fasta=input_fasta,
            output_dir=output_dir,
            threads=threads,
            minsize=minsize,
            config_path=config_path,
            usearch_path=usearch_path,
            asv_fasta_path=asv_fasta_path,
        )
    except (CommandExecutionError, FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("[CLI] USEARCH ASV denoising completed successfully.")
    click.echo(f"[CLI] Final ASV FASTA: {outputs['asv_fasta']}")
    click.echo(f"[CLI] ASV table: {outputs['asv_table']}")


if __name__ == "__main__":
    cli()
