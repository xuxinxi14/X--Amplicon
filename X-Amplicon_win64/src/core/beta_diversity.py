"""Beta diversity utilities for OTU tables."""

from __future__ import annotations

import copy
import re

import numpy as np
import pandas as pd
from skbio import TreeNode
from skbio.diversity import beta_diversity as skbio_beta_diversity

DEFAULT_BETA_METRICS = (
    "braycurtis",
    "jaccard",
    "euclidean",
    "manhattan",
)
PHYLOGENETIC_BETA_METRICS = (
    "unweighted_unifrac",
    "weighted_unifrac",
)
SUPPORTED_BETA_METRICS = DEFAULT_BETA_METRICS + PHYLOGENETIC_BETA_METRICS
HIDDEN_BETA_METRIC_ALIASES = {
    "cityblock": "manhattan",
}
BACKEND_BETA_METRIC_ALIASES = {
    "manhattan": "cityblock",
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
        raise ValueError("otutab must contain only numeric abundance values.") from exc

    if counts.isna().to_numpy().any():
        raise ValueError("otutab must not contain missing values.")

    if (counts < 0).to_numpy().any():
        raise ValueError("otutab must not contain negative values.")

    return counts.astype(np.float64)


def normalize_beta_metric_name(metric: str) -> str:
    if not isinstance(metric, str):
        raise TypeError("metric must be a string.")

    normalized_metric = metric.strip().lower()
    if not normalized_metric:
        raise ValueError("metric must not be empty.")

    canonical_metric = HIDDEN_BETA_METRIC_ALIASES.get(
        normalized_metric, normalized_metric
    )
    if canonical_metric not in SUPPORTED_BETA_METRICS:
        raise ValueError(
            "metric must be one of: braycurtis, jaccard, euclidean, "
            "manhattan, unweighted_unifrac, weighted_unifrac. "
            "'cityblock' is accepted as a hidden alias for 'manhattan'."
        )

    return canonical_metric


def resolve_backend_beta_metric_name(metric: str) -> str:
    canonical_metric = normalize_beta_metric_name(metric)
    return BACKEND_BETA_METRIC_ALIASES.get(canonical_metric, canonical_metric)


def _coerce_labels(labels: pd.Index, label_name: str) -> list[str]:
    coerced = [str(label) for label in labels]
    if len(coerced) != len(set(coerced)):
        raise ValueError(f"{label_name} must remain unique after string conversion.")
    return coerced


def _normalize_taxon_label(label: str) -> str:
    return re.sub(r"[ _]+", "_", label.strip()).lower()


def _prepare_tree(tree: TreeNode | None, taxa_ids: list[str]) -> TreeNode:
    if tree is None:
        raise ValueError("tree is required for phylogenetic beta diversity metrics.")

    if not isinstance(tree, TreeNode):
        raise TypeError("tree must be a skbio.TreeNode instance.")

    resolved_tree = copy.deepcopy(tree)
    tips_by_normalized_name: dict[str, TreeNode] = {}
    for tip in resolved_tree.tips():
        if tip.name is None:
            continue

        normalized_tip_name = _normalize_taxon_label(tip.name)
        if normalized_tip_name in tips_by_normalized_name:
            raise ValueError(
                "tree contains duplicate tip names after normalization: "
                f"{tip.name}"
            )
        tips_by_normalized_name[normalized_tip_name] = tip

    missing_taxa = [
        taxon for taxon in taxa_ids if _normalize_taxon_label(taxon) not in tips_by_normalized_name
    ]
    if missing_taxa:
        raise ValueError(
            "tree is missing OTU IDs required by otutab: "
            f"{missing_taxa[:10]}"
        )

    for taxon in taxa_ids:
        tips_by_normalized_name[_normalize_taxon_label(taxon)].name = taxon

    if len(taxa_ids) == 1:
        return resolved_tree

    return resolved_tree.shear(taxa_ids)


def calculate_beta_distance(
    otutab: pd.DataFrame,
    metric: str,
    tree: TreeNode | None = None,
) -> pd.DataFrame:
    """Calculate a sample-by-sample beta diversity distance matrix.

    Args:
        otutab: OTU table with OTU IDs as rows and sample IDs as columns.
        metric: Distance metric. Supported values are `braycurtis`, `jaccard`,
            `euclidean`, `manhattan`, `unweighted_unifrac`, and
            `weighted_unifrac`. `cityblock` is accepted as a hidden alias for
            `manhattan`.
        tree: Rooted phylogenetic tree required for UniFrac distances.

    Returns:
        A symmetric distance matrix indexed and columned by sample ID.
    """

    counts = _validate_otutab(otutab)
    canonical_metric = normalize_beta_metric_name(metric)
    resolved_metric = resolve_backend_beta_metric_name(canonical_metric)
    sample_ids = _coerce_labels(counts.columns, "Sample IDs")
    observation_data = counts.T.to_numpy(dtype=np.float64, copy=False)

    beta_diversity_kwargs: dict[str, object] = {}
    if resolved_metric == "jaccard":
        observation_data = (observation_data > 0).astype(np.int64)

    if canonical_metric in PHYLOGENETIC_BETA_METRICS:
        taxa_ids = _coerce_labels(counts.index, "OTU IDs")
        beta_diversity_kwargs["taxa"] = taxa_ids
        beta_diversity_kwargs["tree"] = _prepare_tree(tree, taxa_ids)

    distance_matrix = skbio_beta_diversity(
        resolved_metric,
        observation_data,
        ids=sample_ids,
        **beta_diversity_kwargs,
    )
    result = pd.DataFrame(
        distance_matrix.data,
        index=sample_ids,
        columns=sample_ids,
    )
    result.index.name = "SampleID"
    result.columns.name = "SampleID"
    return result
