"""Group-level abundance filtering utilities for OTU tables."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _validate_otutab(otutab: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(otutab, pd.DataFrame):
        raise TypeError("otutab must be a pandas DataFrame.")

    if otutab.empty:
        raise ValueError("otutab must not be empty.")

    if otutab.index.has_duplicates:
        raise ValueError("otutab index contains duplicate OTU IDs.")

    if otutab.columns.has_duplicates:
        raise ValueError("otutab columns contain duplicate sample IDs.")

    try:
        counts = otutab.apply(pd.to_numeric, errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError("otutab must contain only numeric abundance values.") from exc

    if counts.isna().to_numpy().any():
        raise ValueError("otutab must not contain missing values.")

    if (counts < 0).to_numpy().any():
        raise ValueError("otutab must not contain negative values.")

    return counts.astype(np.float64)


def _resolve_group_labels(
    sample_ids: pd.Index,
    metadata: pd.DataFrame,
    group_col: str,
) -> pd.Series:
    if not isinstance(metadata, pd.DataFrame):
        raise TypeError("metadata must be a pandas DataFrame.")

    if metadata.empty:
        raise ValueError("metadata must not be empty.")

    if group_col not in metadata.columns:
        raise ValueError(f"group_col not found in metadata: {group_col}")

    if sample_ids.isin(metadata.index).all():
        aligned_metadata = metadata.loc[sample_ids]
    elif "SampleID" in metadata.columns:
        if metadata["SampleID"].duplicated().any():
            raise ValueError("metadata contains duplicate SampleID values.")
        aligned_metadata = metadata.set_index("SampleID").reindex(sample_ids)
    else:
        missing = [str(sample_id) for sample_id in sample_ids if sample_id not in metadata.index]
        raise ValueError(
            "metadata index must match OTU table sample IDs, or metadata must "
            f"contain a SampleID column. Missing samples: {missing}"
        )

    if aligned_metadata.index.has_duplicates:
        raise ValueError("metadata index contains duplicate sample IDs.")

    if aligned_metadata[group_col].isna().any():
        missing = aligned_metadata.index[aligned_metadata[group_col].isna()].tolist()
        raise ValueError(f"metadata contains missing group labels for samples: {missing}")

    return aligned_metadata[group_col]


def _resolve_threshold(threshold: float) -> float:
    try:
        resolved_threshold = float(threshold)
    except (TypeError, ValueError) as exc:
        raise ValueError("threshold must be a number between 0 and 1.") from exc

    if not 0 <= resolved_threshold <= 1:
        raise ValueError("threshold must be between 0 and 1, where 0.001 means 0.1%.")

    return resolved_threshold * 100.0


def calculate_group_abundance(
    otutab: pd.DataFrame,
    metadata: pd.DataFrame,
    group_col: str,
    threshold: float = 0.001,
) -> pd.DataFrame:
    """Calculate group mean relative abundance and filter low-abundance OTUs.

    Args:
        otutab: OTU table with OTU IDs as rows and sample IDs as columns.
        metadata: Sample metadata. Its index must match the OTU table columns,
            or it must contain a `SampleID` column.
        group_col: Metadata column used to group samples.
        threshold: Minimum group mean abundance expressed as a fraction, so
            `0.001` means `0.1%`.

    Returns:
        A DataFrame indexed by OTU ID and grouped by `group_col`. Values are
        mean relative abundances in percent and each row is retained only if at
        least one group mean is greater than `threshold`.
    """

    counts = _validate_otutab(otutab)
    group_labels = _resolve_group_labels(counts.columns, metadata, group_col)
    sample_totals = counts.sum(axis=0)

    zero_samples = sample_totals.index[sample_totals == 0].tolist()
    if zero_samples:
        raise ValueError(
            f"Relative abundance is undefined for zero-sum samples: {zero_samples}"
        )

    relative_abundance = counts.div(sample_totals, axis=1) * 100.0
    grouped = relative_abundance.T.groupby(group_labels, sort=False).mean().T
    grouped.index.name = otutab.index.name or "OTUID"
    grouped.columns.name = group_col

    threshold_percent = _resolve_threshold(threshold)
    filtered = grouped.loc[grouped.gt(threshold_percent).any(axis=1)]
    return filtered.fillna(0.0)
