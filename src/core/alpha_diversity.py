"""Alpha diversity utilities for OTU tables."""

from __future__ import annotations

from typing import Callable, Sequence

import numpy as np
import pandas as pd

AlphaMetric = Callable[[np.ndarray], float]
RAREFACTION_ITERATIONS = 32
DEFAULT_RAREFACTION_PERCENTAGES = tuple(range(1, 101))


def _load_alpha_metrics() -> dict[str, AlphaMetric]:
    try:
        from skbio.diversity.alpha import ace, chao1, shannon, simpson, sobs
    except ModuleNotFoundError as exc:
        raise ImportError(
            "scikit-bio is required for alpha diversity calculations."
        ) from exc

    return {
        "Observed_OTUs": sobs,
        "Shannon": shannon,
        "Simpson": simpson,
        "Chao1": chao1,
        "ACE": ace,
    }


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
        raise ValueError("otutab must contain only numeric count values.") from exc

    if counts.isna().to_numpy().any():
        raise ValueError("otutab must not contain missing values.")

    if (counts < 0).to_numpy().any():
        raise ValueError("otutab must not contain negative values.")

    rounded = np.round(counts.to_numpy(dtype=np.float64, copy=False))
    if not np.allclose(counts.to_numpy(dtype=np.float64, copy=False), rounded):
        raise ValueError("otutab must contain integer counts.")

    return counts.astype(np.int64)


def _calculate_metrics(counts: np.ndarray) -> dict[str, float]:
    alpha_metrics = _load_alpha_metrics()

    if int(counts.sum()) == 0:
        return {name: 0.0 for name in alpha_metrics}

    metrics: dict[str, float] = {}
    for name, metric in alpha_metrics.items():
        try:
            value = float(metric(counts))
        except (ValueError, ZeroDivisionError):
            value = 0.0

        if np.isnan(value) or np.isinf(value):
            value = 0.0

        metrics[name] = value

    return metrics


def _rarefy_sample(counts: np.ndarray, depth: int) -> np.ndarray:
    return _rarefy_sample_with_rng(counts, depth)


def _rarefy_sample_with_rng(
    counts: np.ndarray,
    depth: int,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    total = int(counts.sum())
    if depth > total or total == 0:
        return np.zeros_like(counts)
    if depth == total:
        return counts.copy()

    pool = np.repeat(np.arange(counts.size, dtype=np.int64), counts)
    if rng is None:
        selected = np.random.choice(pool, size=depth, replace=False)
    else:
        selected = rng.choice(pool, size=depth, replace=False)
    return np.bincount(selected, minlength=counts.size).astype(np.int64)


def _average_rarefied_counts(
    counts: np.ndarray,
    depth: int,
    iterations: int = RAREFACTION_ITERATIONS,
) -> np.ndarray:
    return _average_rarefied_counts_with_seed(counts, depth, iterations=iterations)


def _average_rarefied_counts_with_seed(
    counts: np.ndarray,
    depth: int,
    iterations: int = RAREFACTION_ITERATIONS,
    seed_components: Sequence[int] | None = None,
) -> np.ndarray:
    total = int(counts.sum())
    if depth > total or total == 0:
        return np.zeros_like(counts)
    if depth == total:
        return counts.copy()

    accumulated = np.zeros(counts.size, dtype=np.float64)
    if seed_components is None:
        for _ in range(iterations):
            accumulated += _rarefy_sample_with_rng(counts, depth)
    else:
        base_components = [int(component) for component in seed_components]
        for iteration in range(iterations):
            sample_seed = np.random.SeedSequence([*base_components, iteration + 1])
            rng = np.random.default_rng(sample_seed)
            accumulated += _rarefy_sample_with_rng(counts, depth, rng=rng)

    return np.floor((accumulated / float(iterations)) + 0.5).astype(np.int64)


def _resolve_rarefaction_depth(sample_totals: pd.Series, depth: int) -> int:
    minimum_total = int(sample_totals.min())
    if depth == 0:
        if minimum_total <= 0:
            raise ValueError(
                "rarefaction depth resolves to 0 because at least one sample has no reads."
            )
        return minimum_total

    if depth < 0:
        raise ValueError("rarefaction depth must be 0 or a positive integer.")

    return int(depth)


def rarefy_otutab(
    otutab: pd.DataFrame,
    depth: int = 0,
    seed: int = 1,
) -> tuple[pd.DataFrame, int, list[str]]:
    """Rarefy an OTU table to an equal depth for all eligible samples.

    Args:
        otutab: OTU table with OTU IDs as rows and sample IDs as columns.
        depth: Rarefaction depth. Use 0 to select the minimum sample depth.
        seed: Random seed used for no-replacement rarefaction.

    Returns:
        A tuple of `(rarefied_table, resolved_depth, discarded_samples)`.
        Samples whose total reads are below the resolved depth are discarded.
    """

    counts = _validate_otutab(otutab)
    sample_totals = counts.sum(axis=0)
    resolved_depth = _resolve_rarefaction_depth(sample_totals, int(depth))

    rarefied_samples: dict[str, np.ndarray] = {}
    discarded_samples: list[str] = []
    for sample_index, sample_id in enumerate(counts.columns):
        sample_counts = counts[sample_id].to_numpy(dtype=np.int64, copy=False)
        sample_total = int(sample_counts.sum())
        if sample_total < resolved_depth:
            discarded_samples.append(str(sample_id))
            continue

        sample_seed = np.random.SeedSequence([int(seed), sample_index + 1, resolved_depth])
        rng = np.random.default_rng(sample_seed)
        rarefied_samples[str(sample_id)] = _rarefy_sample_with_rng(
            sample_counts,
            resolved_depth,
            rng=rng,
        )

    if not rarefied_samples:
        raise ValueError("No samples remain after OTU table rarefaction.")

    result = pd.DataFrame(
        rarefied_samples,
        index=counts.index,
        dtype=np.int64,
    )
    result.index.name = counts.index.name or "#OTUID"
    return result, resolved_depth, discarded_samples


def calculate_richness_rarefaction_curve(
    otutab: pd.DataFrame,
    percentages: Sequence[int] = DEFAULT_RAREFACTION_PERCENTAGES,
    seed: int = 1,
) -> pd.DataFrame:
    """Calculate a USEARCH-style rarefaction curve table for observed richness.

    Args:
        otutab: OTU table with OTU IDs as rows and sample IDs as columns.
        percentages: Integer percentages used to subsample each sample.
        seed: Random seed used for no-replacement rarefaction.

    Returns:
        A wide-format DataFrame whose index is the requested percentage and whose
        columns are sample IDs. The index name is `richness`.
    """

    counts = _validate_otutab(otutab)
    observed_metric = _load_alpha_metrics()["Observed_OTUs"]

    resolved_percentages: list[int] = []
    for percentage in percentages:
        if not isinstance(percentage, (int, np.integer)):
            raise TypeError("Each rarefaction percentage must be an integer.")
        resolved_percentage = int(percentage)
        if resolved_percentage < 1 or resolved_percentage > 100:
            raise ValueError("Each rarefaction percentage must be between 1 and 100.")
        resolved_percentages.append(resolved_percentage)

    if not resolved_percentages:
        raise ValueError("percentages must not be empty.")

    richness_by_percentage: dict[int, dict[str, float]] = {}
    for percentage in resolved_percentages:
        sample_values: dict[str, float] = {}
        for sample_index, sample_id in enumerate(counts.columns):
            sample_counts = counts[sample_id].to_numpy(dtype=np.int64, copy=False)
            total = int(sample_counts.sum())
            if total == 0:
                sample_values[str(sample_id)] = 0.0
                continue

            depth = max(1, int(np.floor((total * percentage) / 100.0)))
            depth = min(depth, total)
            rarefied_counts = _average_rarefied_counts_with_seed(
                sample_counts,
                depth,
                iterations=RAREFACTION_ITERATIONS,
                seed_components=(int(seed), sample_index + 1, percentage),
            )
            value = float(observed_metric(rarefied_counts))
            if np.isnan(value) or np.isinf(value):
                value = 0.0
            sample_values[str(sample_id)] = value

        richness_by_percentage[percentage] = sample_values

    result = pd.DataFrame.from_dict(richness_by_percentage, orient="index")
    result.index.name = "richness"
    return result.loc[resolved_percentages, list(counts.columns)].fillna(0.0)


def calculate_alpha_diversity(otutab: pd.DataFrame) -> pd.DataFrame:
    """Calculate alpha diversity metrics for each sample in an OTU table.

    Args:
        otutab: OTU table with OTU IDs as rows and sample IDs as columns.

    Returns:
        A DataFrame indexed by sample ID. Columns contain `Observed_OTUs`,
        `Shannon`, `Simpson`, `Chao1`, and `ACE`.
    """

    counts = _validate_otutab(otutab)

    records: dict[str, dict[str, float]] = {}
    for sample_id in counts.columns:
        sample_counts = counts[sample_id].to_numpy(dtype=np.int64, copy=False)
        records[str(sample_id)] = _calculate_metrics(sample_counts)

    metric_order = list(_load_alpha_metrics())
    result = pd.DataFrame.from_dict(records, orient="index")
    result.index.name = "SampleID"
    return result.loc[:, metric_order].fillna(0.0)


def calculate_rarefaction_curve(
    otutab: pd.DataFrame,
    depths: list[int],
) -> pd.DataFrame:
    """Calculate rarefaction curves for each sample at the requested depths.

    Args:
        otutab: OTU table with OTU IDs as rows and sample IDs as columns.
        depths: Rarefaction depths. Each depth must be a positive integer.

    Returns:
        A long-format DataFrame with one row per sample-depth pair. Columns are
        `SampleID`, `Depth`, `Observed_OTUs`, `Shannon`, `Simpson`, `Chao1`,
        and `ACE`. Each depth is estimated from repeated no-replacement
        rarefactions, and empty results are filled with `0.0`.
    """

    counts = _validate_otutab(otutab)
    metric_order = list(_load_alpha_metrics())

    if not depths:
        raise ValueError("depths must not be empty.")

    resolved_depths: list[int] = []
    for depth in depths:
        if not isinstance(depth, (int, np.integer)):
            raise TypeError("Each rarefaction depth must be an integer.")
        if int(depth) <= 0:
            raise ValueError("Each rarefaction depth must be greater than zero.")
        resolved_depths.append(int(depth))

    records: list[dict[str, float | int | str]] = []
    for sample_id in counts.columns:
        sample_counts = counts[sample_id].to_numpy(dtype=np.int64, copy=False)
        for depth in resolved_depths:
            rarefied_counts = _average_rarefied_counts(sample_counts, depth)
            metrics = _calculate_metrics(rarefied_counts)
            records.append(
                {
                    "SampleID": str(sample_id),
                    "Depth": depth,
                    **metrics,
                }
            )

    column_order = ["SampleID", "Depth", *metric_order]
    return pd.DataFrame.from_records(records, columns=column_order).fillna(0.0)
