"""Metadata validation for Web UI project setup."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

from webui.backend.config import resolve_path
from webui.backend.models.project import GroupSummary, MetadataValidationResult


def read_metadata_table(metadata_path: str, *, base_dir: str | Path | None = None) -> tuple[Path, pd.DataFrame]:
    """Read a metadata TSV as strings."""

    resolved_path = resolve_path(metadata_path, base_dir)
    table = pd.read_csv(resolved_path, sep="\t", header=0, dtype=str, keep_default_na=False)
    return resolved_path, table


def validate_metadata(
    metadata_path: str,
    *,
    sample_id_col: str = "SampleID",
    group_col: str = "Group",
    base_dir: str | Path | None = None,
) -> MetadataValidationResult:
    """Validate metadata and return user-facing diagnostics."""

    resolved_path = resolve_path(metadata_path, base_dir)
    result = MetadataValidationResult(
        status="failed",
        metadata_path=str(resolved_path),
        sample_id_col=sample_id_col,
        group_col=group_col,
    )

    if not resolved_path.is_file():
        result.messages.append(f"Metadata file was not found: {resolved_path}")
        result.suggestions.append("Select a tab-delimited metadata table before running analysis.")
        return result
    result.exists = True

    try:
        _, table = read_metadata_table(str(resolved_path))
    except Exception as exc:
        result.messages.append(f"Metadata file could not be read: {exc}")
        result.suggestions.append("Check that the file is a UTF-8 or system-encoded tab-delimited text table.")
        return result

    result.readable = True
    result.rows = int(table.shape[0])
    result.columns = int(table.shape[1])
    result.column_names = [str(column) for column in table.columns]

    if table.empty:
        result.messages.append("Metadata table does not contain any sample rows.")
        result.suggestions.append("Add at least one sample row to the metadata table.")
        return result

    if sample_id_col not in table.columns:
        result.missing_columns.append(sample_id_col)
    if group_col not in table.columns:
        result.missing_columns.append(group_col)

    if result.missing_columns:
        result.messages.append("Metadata table is missing required columns: " + ", ".join(result.missing_columns))
        result.suggestions.append("Confirm the SampleID and Group column names, or choose the correct columns in the UI.")
        return result

    sample_values = table[sample_id_col].fillna("").astype(str).str.strip()
    group_values = table[group_col].fillna("").astype(str).str.strip()
    result.empty_sample_ids = int((sample_values == "").sum())
    result.empty_group_values = int((group_values == "").sum())
    result.sample_count = int((sample_values != "").sum())

    counts = Counter(sample_values[sample_values != ""])
    result.duplicate_sample_ids = sorted(sample_id for sample_id, count in counts.items() if count > 1)

    for group_name in sorted(group_values[group_values != ""].unique()):
        samples = [
            str(sample)
            for sample in table.loc[group_values == group_name, sample_id_col].fillna("").astype(str).str.strip()
            if str(sample)
        ]
        result.groups.append(GroupSummary(group=str(group_name), count=len(samples), samples=samples))

    if result.empty_sample_ids:
        result.messages.append(f"Metadata contains {result.empty_sample_ids} empty SampleID value(s).")
    if result.duplicate_sample_ids:
        result.messages.append("Metadata contains duplicate SampleID values: " + ", ".join(result.duplicate_sample_ids[:10]))
    if result.empty_group_values:
        result.messages.append(f"Metadata contains {result.empty_group_values} empty group value(s).")
    if not result.groups:
        result.messages.append("No non-empty group values were found.")

    if result.empty_sample_ids or result.duplicate_sample_ids:
        result.status = "failed"
        result.suggestions.append("Fix empty or duplicated SampleID values before running the pipeline.")
    elif result.empty_group_values or not result.groups:
        result.status = "warning"
        result.suggestions.append("Group information is incomplete; downstream visualization/statistics may be limited.")
    else:
        result.status = "passed"
        result.messages.append(f"Metadata is valid: {result.sample_count} samples in {len(result.groups)} group(s).")

    return result


def sample_ids_from_metadata(
    metadata_path: str,
    *,
    sample_id_col: str = "SampleID",
    base_dir: str | Path | None = None,
) -> tuple[Path, list[str]]:
    """Return sample IDs from metadata after basic validation."""

    resolved_path, table = read_metadata_table(metadata_path, base_dir=base_dir)
    if sample_id_col not in table.columns:
        raise ValueError(f"Metadata is missing sample ID column: {sample_id_col}")
    samples = [str(value).strip() for value in table[sample_id_col].fillna("").tolist()]
    samples = [sample for sample in samples if sample]
    return resolved_path, samples
