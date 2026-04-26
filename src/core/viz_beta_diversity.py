"""Beta diversity visualization tools for X-Amplicon outputs."""

from __future__ import annotations

try:
    import matplotlib
except ModuleNotFoundError:
    matplotlib = None
else:
    matplotlib.use("Agg")

import math
import os
from typing import Any, Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import squareform
from scipy.stats import chi2, rankdata

from .viz_common import (
    DEFAULT_BETA_CPCOA_DIR,
    DEFAULT_BETA_HEATMAP_DIR,
    DEFAULT_BETA_PCOA_DIR,
    GROUP_COLORS,
    build_sample_metadata,
    ensure_output_dir,
    find_beta_distance_files,
    normalize_metric_title,
    plotly_palette,
    read_distance_matrix,
    sanitize_id,
    validate_output_format,
    write_html_dashboard,
    write_html_figure,
    write_static_figure,
    write_table,
)


def _generate_group_colors(groups: Sequence[str]) -> dict[str, str]:
    colors = dict(GROUP_COLORS)
    palette = plotly_palette()
    for group in dict.fromkeys(str(group) for group in groups):
        if group not in colors:
            colors[group] = palette[len(colors) % len(palette)]
    return colors


def _pcoa(distance_matrix: pd.DataFrame, n_components: int = 2) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    values = distance_matrix.to_numpy(dtype=float)
    n = values.shape[0]
    centered = np.eye(n) - np.ones((n, n)) / n
    gram = -0.5 * centered.dot(values ** 2).dot(centered)
    eigvals, eigvecs = np.linalg.eigh(gram)
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]

    positive = np.maximum(eigvals, 0.0)
    coordinates = eigvecs[:, :n_components] * np.sqrt(positive[:n_components])
    if coordinates.shape[1] < n_components:
        coordinates = np.pad(
            coordinates,
            ((0, 0), (0, n_components - coordinates.shape[1])),
            mode="constant",
        )
    total = positive.sum()
    explained = np.zeros(n_components, dtype=float)
    if total > 0:
        explained = (positive[:n_components] / total) * 100.0

    columns = [f"PCoA{index + 1}" for index in range(n_components)]
    coords = pd.DataFrame(coordinates, index=distance_matrix.index.astype(str), columns=columns)
    coords.index.name = "SampleID"
    return coords, explained, eigvals


def _ellipse_trace(
    points: pd.DataFrame,
    group: str,
    color: str,
    confidence: float,
) -> go.Scatter | None:
    if len(points) < 3:
        return None
    values = points[["Axis1", "Axis2"]].to_numpy(dtype=float)
    covariance = np.cov(values, rowvar=False)
    if not np.all(np.isfinite(covariance)):
        return None
    eigvals, eigvecs = np.linalg.eigh(covariance)
    if np.any(eigvals <= 0):
        return None
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]
    radius = math.sqrt(float(chi2.ppf(confidence, df=2)))
    theta = np.linspace(0, 2 * np.pi, 120)
    circle = np.column_stack([np.cos(theta), np.sin(theta)])
    ellipse = circle.dot(np.diag(np.sqrt(eigvals) * radius)).dot(eigvecs.T)
    center = values.mean(axis=0)
    ellipse += center
    return go.Scatter(
        x=ellipse[:, 0],
        y=ellipse[:, 1],
        mode="lines",
        name=f"{group} ellipse",
        line={"color": color, "width": 1.5, "dash": "dot"},
        hoverinfo="skip",
        showlegend=False,
    )


def _build_ordination_figure(
    plot_df: pd.DataFrame,
    metric: str,
    axis_prefix: str,
    axis_percent: Sequence[float],
    title: str,
    show_labels: bool,
    ellipse_confidence: float,
) -> go.Figure:
    group_colors = _generate_group_colors(plot_df["Group"].astype(str).tolist())
    fig = go.Figure()
    for group, group_df in plot_df.groupby("Group", sort=False):
        color = group_colors[str(group)]
        fig.add_trace(
            go.Scatter(
                x=group_df["Axis1"],
                y=group_df["Axis2"],
                mode="markers+text" if show_labels else "markers",
                text=group_df["SampleID"] if show_labels else None,
                textposition="top center",
                name=str(group),
                marker={"size": 12, "color": color, "line": {"color": "white", "width": 0.8}},
                customdata=group_df[["SampleID", "Group"]],
                hovertemplate=(
                    "Sample: %{customdata[0]}<br>"
                    "Group: %{customdata[1]}<br>"
                    f"{axis_prefix}1: %{{x:.4f}}<br>"
                    f"{axis_prefix}2: %{{y:.4f}}<extra></extra>"
                ),
            )
        )
        ellipse = _ellipse_trace(group_df, str(group), color, ellipse_confidence)
        if ellipse is not None:
            fig.add_trace(ellipse)

    fig.update_layout(
        title={"text": title, "x": 0.5},
        template="plotly_white",
        width=900,
        height=650,
        legend_title_text="Group",
        xaxis_title=f"{axis_prefix}1 ({axis_percent[0]:.2f}%)",
        yaxis_title=f"{axis_prefix}2 ({axis_percent[1]:.2f}%)",
    )
    fig.add_hline(y=0, line_width=1, line_dash="dash", line_color="#d0d0d0")
    fig.add_vline(x=0, line_width=1, line_dash="dash", line_color="#d0d0d0")
    return fig


def _write_optional_static(
    fig: Any,
    base_path: str,
    output_format: str,
    width: int,
    height: int,
    generated_files: list[str],
    skipped_static: list[str],
) -> None:
    if output_format not in {"png", "pdf", "all"}:
        return
    for suffix in ("png", "pdf"):
        if output_format not in {suffix, "all"}:
            continue
        static_path = f"{base_path}.{suffix}"
        written = write_static_figure(fig, static_path, width=width, height=height)
        if written is None:
            skipped_static.append(static_path)
        else:
            generated_files.append(written)


def plot_beta_pcoa(
    beta_dir: str = "work/06_final/beta",
    metadata_path: str | None = "work/00_input/metadata.txt",
    output_dir: str = DEFAULT_BETA_PCOA_DIR,
    metrics: list[str] | None = None,
    sample_id_col: str = "SampleID",
    group_col: str = "Group",
    show_labels: bool = False,
    ellipse_confidence: float = 0.95,
    output_format: str = "html",
) -> dict[str, Any]:
    """Generate beta diversity PCoA scatter plots.

    Args:
        beta_dir: Directory containing beta distance matrices.
        metadata_path: Metadata TSV used for group colors. If missing, groups
            are inferred from sample IDs.
        output_dir: Directory for generated plots and coordinate tables.
        metrics: Metrics to process. Defaults to all matrix files found.
        sample_id_col: Metadata column containing sample IDs.
        group_col: Metadata column containing group labels.
        show_labels: Whether to draw sample IDs next to points.
        ellipse_confidence: Confidence level for group ellipses.
        output_format: `html`, `png`, `pdf`, or `all`. Static formats require
            kaleido; HTML is always attempted.

    Returns:
        A dictionary describing generated files and skipped static exports.

    Raises:
        FileNotFoundError: If required input files are missing.
        ValueError: If matrices or metadata cannot be matched.
    """

    output_format = validate_output_format(output_format)
    if not 0 < float(ellipse_confidence) < 1:
        raise ValueError("ellipse_confidence must be between 0 and 1.")

    resolved_output_dir = ensure_output_dir(output_dir)
    file_map = find_beta_distance_files(beta_dir, metrics=metrics)
    generated_files: list[str] = []
    skipped_static: list[str] = []
    figures: dict[str, Any] = {}
    coordinate_tables: list[pd.DataFrame] = []

    for metric, path in file_map.items():
        distance_matrix = read_distance_matrix(path, metric)
        coords, explained, _eigvals = _pcoa(distance_matrix, n_components=2)
        sample_meta = build_sample_metadata(
            coords.index.tolist(),
            metadata_path=metadata_path,
            sample_id_col=sample_id_col,
            group_col=group_col,
        )
        plot_df = coords.reset_index().merge(sample_meta, on="SampleID", how="left")
        plot_df = plot_df.rename(columns={"PCoA1": "Axis1", "PCoA2": "Axis2"})
        plot_df.insert(0, "Metric", metric)
        plot_df.insert(1, "PCoA1_percent", float(explained[0]))
        plot_df.insert(2, "PCoA2_percent", float(explained[1]))
        coordinate_tables.append(plot_df.copy())

        title = f"Beta Diversity PCoA - {normalize_metric_title(metric)}"
        fig = _build_ordination_figure(
            plot_df,
            metric,
            axis_prefix="PCoA",
            axis_percent=explained,
            title=title,
            show_labels=show_labels,
            ellipse_confidence=float(ellipse_confidence),
        )
        figures[normalize_metric_title(metric)] = fig

        if output_format in {"html", "all"}:
            generated_files.append(
                write_html_figure(
                    fig,
                    os.path.join(resolved_output_dir, f"beta_pcoa_{metric}.html"),
                )
            )
        _write_optional_static(
            fig,
            os.path.join(resolved_output_dir, f"beta_pcoa_{metric}"),
            output_format,
            width=900,
            height=650,
            generated_files=generated_files,
            skipped_static=skipped_static,
        )

    coordinates = pd.concat(coordinate_tables, ignore_index=True)
    coordinates_path = write_table(
        coordinates,
        os.path.join(resolved_output_dir, "beta_pcoa_coordinates.tsv"),
        include_index=False,
    )
    generated_files.insert(0, coordinates_path)
    if output_format in {"html", "all"}:
        generated_files.append(
            write_html_dashboard(
                figures,
                os.path.join(resolved_output_dir, "beta_pcoa_report.html"),
                "Beta Diversity PCoA",
            )
        )

    return {
        "beta_dir": os.path.abspath(beta_dir),
        "metadata": None if metadata_path is None else os.path.abspath(metadata_path),
        "output_dir": resolved_output_dir,
        "metrics": list(file_map),
        "coordinates": coordinates_path,
        "plots": generated_files,
        "skipped_static_exports": skipped_static,
    }


def _design_matrix(groups: Sequence[str]) -> np.ndarray:
    group_list = list(dict.fromkeys(str(group) for group in groups))
    matrix = np.zeros((len(groups), len(group_list)), dtype=float)
    for row_index, group in enumerate(groups):
        matrix[row_index, group_list.index(str(group))] = 1.0
    return matrix


def _projection_matrix(matrix: np.ndarray) -> np.ndarray:
    return matrix.dot(np.linalg.pinv(matrix.T.dot(matrix))).dot(matrix.T)


def _run_cpcoa(distance_matrix: pd.DataFrame, groups: Sequence[str]) -> tuple[pd.DataFrame, dict[str, float], np.ndarray]:
    coords, _explained, eigvals = _pcoa(distance_matrix, n_components=max(2, len(distance_matrix) - 1))
    positive_columns = [
        column for index, column in enumerate(coords.columns)
        if index < len(eigvals) and eigvals[index] > 1e-12
    ]
    response = coords[positive_columns].to_numpy(dtype=float) if positive_columns else coords.to_numpy(dtype=float)
    x = _design_matrix(groups)
    fitted = _projection_matrix(x).dot(response)
    residual = response - fitted
    constrained = float(np.sum(fitted ** 2))
    unconstrained = float(np.sum(residual ** 2))
    total = constrained + unconstrained

    centered_fitted = fitted - fitted.mean(axis=0, keepdims=True)
    u, singular_values, _vt = np.linalg.svd(centered_fitted, full_matrices=False)
    variances = singular_values ** 2
    axes = u[:, :2] * singular_values[:2]
    if axes.shape[1] < 2:
        axes = np.pad(axes, ((0, 0), (0, 2 - axes.shape[1])), mode="constant")

    constrained_total = variances.sum()
    cap_percent = np.zeros(2, dtype=float)
    if constrained_total > 0:
        cap_percent = (variances[:2] / constrained_total) * 100.0
    constrained_percent = (constrained / total) * 100.0 if total > 0 else 0.0

    coord_df = pd.DataFrame(
        {
            "SampleID": distance_matrix.index.astype(str).tolist(),
            "Group": list(groups),
            "Axis1": axes[:, 0],
            "Axis2": axes[:, 1],
        }
    )
    stats = {
        "constrained_percent": constrained_percent,
        "CAP1_percent": float(cap_percent[0]),
        "CAP2_percent": float(cap_percent[1]),
        "constrained_inertia": constrained,
        "unconstrained_inertia": unconstrained,
    }
    return coord_df, stats, response


def _pseudo_f_from_response(response: np.ndarray, groups: Sequence[str]) -> float:
    x = _design_matrix(groups)
    fitted = _projection_matrix(x).dot(response)
    residual = response - fitted
    constrained = float(np.sum(fitted ** 2))
    unconstrained = float(np.sum(residual ** 2))
    group_count = len(set(str(group) for group in groups))
    df_model = group_count - 1
    df_residual = len(groups) - group_count
    if df_model <= 0 or df_residual <= 0 or unconstrained <= 0:
        return math.nan
    return (constrained / df_model) / (unconstrained / df_residual)


def _permutation_p_value(
    response: np.ndarray,
    groups: Sequence[str],
    observed_f: float,
    permutations: int,
    seed: int,
) -> float:
    if not np.isfinite(observed_f):
        return math.nan
    if permutations <= 0:
        return math.nan
    rng = np.random.default_rng(seed)
    labels = np.asarray(list(groups), dtype=object)
    more_extreme = 1
    for _ in range(int(permutations)):
        permuted_f = _pseudo_f_from_response(response, rng.permutation(labels))
        if np.isfinite(permuted_f) and permuted_f >= observed_f:
            more_extreme += 1
    return more_extreme / (int(permutations) + 1)


def plot_beta_cpcoa(
    beta_dir: str = "work/06_final/beta",
    metadata_path: str | None = "work/00_input/metadata.txt",
    output_dir: str = DEFAULT_BETA_CPCOA_DIR,
    metrics: list[str] | None = None,
    sample_id_col: str = "SampleID",
    group_col: str = "Group",
    permutations: int = 999,
    random_seed: int = 20260426,
    show_labels: bool = False,
    ellipse_confidence: float = 0.68,
    output_format: str = "html",
) -> dict[str, Any]:
    """Generate constrained PCoA plots grouped by metadata.

    Args:
        beta_dir: Directory containing beta distance matrices.
        metadata_path: Metadata TSV used for the constrained grouping factor.
        output_dir: Directory for generated plots and coordinate tables.
        metrics: Metrics to process. Defaults to all matrix files found.
        sample_id_col: Metadata column containing sample IDs.
        group_col: Metadata column containing group labels.
        permutations: Permutation count for pseudo-F p-value.
        random_seed: Random seed for permutations.
        show_labels: Whether to draw sample IDs next to points.
        ellipse_confidence: Confidence level for group ellipses.
        output_format: `html`, `png`, `pdf`, or `all`. Static formats require
            kaleido; HTML is always attempted.

    Returns:
        A dictionary describing generated files and skipped static exports.

    Raises:
        FileNotFoundError: If required input files are missing.
        ValueError: If matrices or metadata cannot be matched.
    """

    output_format = validate_output_format(output_format)
    if int(permutations) < 0:
        raise ValueError("permutations must be greater than or equal to 0.")
    if not 0 < float(ellipse_confidence) < 1:
        raise ValueError("ellipse_confidence must be between 0 and 1.")

    resolved_output_dir = ensure_output_dir(output_dir)
    file_map = find_beta_distance_files(beta_dir, metrics=metrics)
    generated_files: list[str] = []
    skipped_static: list[str] = []
    figures: dict[str, Any] = {}
    coordinate_tables: list[pd.DataFrame] = []
    stat_rows: list[dict[str, Any]] = []

    for metric, path in file_map.items():
        distance_matrix = read_distance_matrix(path, metric)
        sample_meta = build_sample_metadata(
            distance_matrix.index.tolist(),
            metadata_path=metadata_path,
            sample_id_col=sample_id_col,
            group_col=group_col,
        )
        groups = sample_meta["Group"].astype(str).tolist()
        coord_df, stats, response = _run_cpcoa(distance_matrix, groups)
        observed_f = _pseudo_f_from_response(response, groups)
        p_value = _permutation_p_value(
            response,
            groups,
            observed_f,
            permutations=int(permutations),
            seed=int(random_seed),
        )
        stats["pseudo_f"] = observed_f
        stats["p_value"] = p_value

        coord_out = coord_df.copy()
        coord_out.insert(0, "Metric", metric)
        coord_out.insert(1, "Constrained_percent", stats["constrained_percent"])
        coord_out.insert(2, "CAP1_percent", stats["CAP1_percent"])
        coord_out.insert(3, "CAP2_percent", stats["CAP2_percent"])
        coordinate_tables.append(coord_out)
        stat_rows.append({"Metric": metric, **stats})

        title = (
            f"Beta Diversity CPCoA - {normalize_metric_title(metric)}"
            f"<br><sup>pseudo-F={observed_f:.3f}, p={p_value:.4g}</sup>"
        )
        fig = _build_ordination_figure(
            coord_df,
            metric,
            axis_prefix="CAP",
            axis_percent=[stats["CAP1_percent"], stats["CAP2_percent"]],
            title=title,
            show_labels=show_labels,
            ellipse_confidence=float(ellipse_confidence),
        )
        figures[normalize_metric_title(metric)] = fig

        if output_format in {"html", "all"}:
            generated_files.append(
                write_html_figure(
                    fig,
                    os.path.join(resolved_output_dir, f"beta_cpcoa_{metric}.html"),
                )
            )
        _write_optional_static(
            fig,
            os.path.join(resolved_output_dir, f"beta_cpcoa_{metric}"),
            output_format,
            width=900,
            height=650,
            generated_files=generated_files,
            skipped_static=skipped_static,
        )

    coordinates_path = write_table(
        pd.concat(coordinate_tables, ignore_index=True),
        os.path.join(resolved_output_dir, "beta_cpcoa_coordinates.tsv"),
        include_index=False,
    )
    stats_path = write_table(
        pd.DataFrame(stat_rows),
        os.path.join(resolved_output_dir, "beta_cpcoa_stats.tsv"),
        include_index=False,
    )
    generated_files.insert(0, stats_path)
    generated_files.insert(0, coordinates_path)
    if output_format in {"html", "all"}:
        generated_files.append(
            write_html_dashboard(
                figures,
                os.path.join(resolved_output_dir, "beta_cpcoa_report.html"),
                "Beta Diversity CPCoA",
            )
        )

    return {
        "beta_dir": os.path.abspath(beta_dir),
        "metadata": None if metadata_path is None else os.path.abspath(metadata_path),
        "output_dir": resolved_output_dir,
        "metrics": list(file_map),
        "coordinates": coordinates_path,
        "stats": stats_path,
        "plots": generated_files,
        "skipped_static_exports": skipped_static,
    }


def _run_permanova(distance_matrix: pd.DataFrame, groups: Sequence[str], permutations: int, seed: int) -> dict[str, Any]:
    if len(set(groups)) < 2:
        return {"method": "PERMANOVA", "statistic": math.nan, "p_value": math.nan, "r2": math.nan}
    try:
        from skbio.stats.distance import DistanceMatrix, permanova

        dm = DistanceMatrix(distance_matrix.to_numpy(dtype=float), ids=distance_matrix.index.tolist())
        result = permanova(dm, grouping=list(groups), permutations=int(permutations))
        return {
            "method": "PERMANOVA",
            "statistic": float(result.get("test statistic", math.nan)),
            "p_value": float(result.get("p-value", math.nan)),
            "r2": math.nan,
        }
    except Exception:
        labels = np.asarray(list(groups), dtype=object)
        values = distance_matrix.to_numpy(dtype=float)
        n = len(labels)
        unique_groups = np.unique(labels)

        def pseudo_f(current: np.ndarray) -> tuple[float, float]:
            total_ss = float(np.sum(values ** 2) / n)
            within_ss = 0.0
            for group in unique_groups:
                idx = np.where(current == group)[0]
                if len(idx):
                    within_ss += float(np.sum(values[np.ix_(idx, idx)] ** 2) / len(idx))
            among_ss = max(total_ss - within_ss, 0.0)
            df_among = len(unique_groups) - 1
            df_within = n - len(unique_groups)
            if df_among <= 0 or df_within <= 0 or within_ss <= 0:
                return math.nan, math.nan
            return (among_ss / df_among) / (within_ss / df_within), among_ss / total_ss if total_ss else math.nan

        observed, r2 = pseudo_f(labels)
        rng = np.random.default_rng(seed)
        more_extreme = 1
        for _ in range(max(0, int(permutations))):
            permuted, _r2 = pseudo_f(rng.permutation(labels))
            if np.isfinite(permuted) and permuted >= observed:
                more_extreme += 1
        p_value = more_extreme / (int(permutations) + 1) if permutations > 0 else math.nan
        return {"method": "PERMANOVA", "statistic": observed, "p_value": p_value, "r2": r2}


def _run_anosim(distance_matrix: pd.DataFrame, groups: Sequence[str], permutations: int, seed: int) -> dict[str, Any]:
    if len(set(groups)) < 2:
        return {"method": "ANOSIM", "statistic": math.nan, "p_value": math.nan, "r2": math.nan}
    try:
        from skbio.stats.distance import DistanceMatrix, anosim

        dm = DistanceMatrix(distance_matrix.to_numpy(dtype=float), ids=distance_matrix.index.tolist())
        result = anosim(dm, grouping=list(groups), permutations=int(permutations))
        return {
            "method": "ANOSIM",
            "statistic": float(result.get("test statistic", math.nan)),
            "p_value": float(result.get("p-value", math.nan)),
            "r2": math.nan,
        }
    except Exception:
        condensed = squareform(distance_matrix.to_numpy(dtype=float), checks=False)
        ranks = rankdata(condensed)
        labels = np.asarray(list(groups), dtype=object)
        n = len(labels)
        pairs = [(i, j) for i in range(n - 1) for j in range(i + 1, n)]

        def r_stat(current: np.ndarray) -> float:
            within: list[float] = []
            between: list[float] = []
            for rank, (i, j) in zip(ranks, pairs):
                if current[i] == current[j]:
                    within.append(float(rank))
                else:
                    between.append(float(rank))
            if not within or not between:
                return math.nan
            return (float(np.mean(between)) - float(np.mean(within))) / (n * (n - 1) / 4.0)

        observed = r_stat(labels)
        rng = np.random.default_rng(seed)
        more_extreme = 1
        for _ in range(max(0, int(permutations))):
            permuted = r_stat(rng.permutation(labels))
            if np.isfinite(permuted) and permuted >= observed:
                more_extreme += 1
        p_value = more_extreme / (int(permutations) + 1) if permutations > 0 else math.nan
        return {"method": "ANOSIM", "statistic": observed, "p_value": p_value, "r2": math.nan}


def _cluster_order(distance_matrix: pd.DataFrame, enabled: bool) -> list[int]:
    if not enabled or len(distance_matrix) < 3:
        return list(range(len(distance_matrix)))
    condensed = squareform(distance_matrix.to_numpy(dtype=float), checks=False)
    return list(map(int, leaves_list(linkage(condensed, method="average"))))


def _discrete_colorscale(colors: Sequence[str]) -> list[list[Any]]:
    if not colors:
        return [[0.0, "#cccccc"], [1.0, "#cccccc"]]
    if len(colors) == 1:
        return [[0.0, colors[0]], [1.0, colors[0]]]
    scale: list[list[Any]] = []
    step = 1.0 / len(colors)
    for index, color in enumerate(colors):
        scale.append([index * step, color])
        scale.append([(index + 1) * step - 1e-9, color])
    scale[-1][0] = 1.0
    return scale


def _build_beta_heatmap(
    distance_matrix: pd.DataFrame,
    sample_meta: pd.DataFrame,
    metric: str,
    cluster_samples: bool,
    permanova: dict[str, Any],
    anosim: dict[str, Any],
) -> go.Figure:
    order = _cluster_order(distance_matrix, cluster_samples)
    ordered_samples = [distance_matrix.index[index] for index in order]
    ordered = distance_matrix.loc[ordered_samples, ordered_samples]
    groups = sample_meta.set_index("SampleID").loc[ordered_samples, "Group"].astype(str).tolist()
    group_colors = _generate_group_colors(groups)
    group_order = list(dict.fromkeys(groups))
    group_codes = [[group_order.index(group) for group in groups]]
    group_scale = _discrete_colorscale([group_colors[group] for group in group_order])

    customdata = np.empty((len(ordered), len(ordered), 4), dtype=object)
    for row_index, row_sample in enumerate(ordered_samples):
        for col_index, col_sample in enumerate(ordered_samples):
            customdata[row_index, col_index] = [
                row_sample,
                col_sample,
                groups[row_index],
                groups[col_index],
            ]

    fig = make_subplots(
        rows=2,
        cols=1,
        row_heights=[0.07, 0.93],
        shared_xaxes=True,
        vertical_spacing=0.02,
    )
    fig.add_trace(
        go.Heatmap(
            z=group_codes,
            x=ordered_samples,
            y=["Group"],
            colorscale=group_scale,
            showscale=False,
            hovertemplate="Sample: %{x}<br>Group code: %{z}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Heatmap(
            z=ordered.to_numpy(dtype=float),
            x=ordered_samples,
            y=ordered_samples,
            colorscale="RdYlBu_r",
            colorbar={"title": "Distance"},
            customdata=customdata,
            hovertemplate=(
                "%{customdata[0]} vs %{customdata[1]}<br>"
                "Groups: %{customdata[2]} / %{customdata[3]}<br>"
                "Distance: %{z:.4f}<extra></extra>"
            ),
        ),
        row=2,
        col=1,
    )
    for group in group_order:
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker={"size": 10, "color": group_colors[group], "symbol": "square"},
                name=group,
                showlegend=True,
            ),
            row=2,
            col=1,
        )

    stats_text = (
        f"PERMANOVA F={permanova.get('statistic', math.nan):.3f}, "
        f"p={permanova.get('p_value', math.nan):.4g}; "
        f"ANOSIM R={anosim.get('statistic', math.nan):.3f}, "
        f"p={anosim.get('p_value', math.nan):.4g}"
    )
    fig.update_layout(
        title={"text": f"Beta Distance Heatmap - {normalize_metric_title(metric)}<br><sup>{stats_text}</sup>", "x": 0.5},
        template="plotly_white",
        width=980,
        height=860,
        legend_title_text="Group",
        margin={"l": 80, "r": 120, "t": 90, "b": 90},
    )
    fig.update_xaxes(tickangle=90, row=2, col=1)
    fig.update_yaxes(autorange="reversed", row=2, col=1)
    return fig


def _within_between_distances(
    distance_matrix: pd.DataFrame,
    sample_meta: pd.DataFrame,
    metric: str,
) -> pd.DataFrame:
    group_map = sample_meta.set_index("SampleID")["Group"].astype(str).to_dict()
    rows: list[dict[str, Any]] = []
    samples = distance_matrix.index.astype(str).tolist()
    for left_index, left_sample in enumerate(samples):
        for right_sample in samples[left_index + 1:]:
            left_group = group_map[left_sample]
            right_group = group_map[right_sample]
            relation = "Within-group" if left_group == right_group else "Between-group"
            rows.append(
                {
                    "metric": metric,
                    "sample_a": left_sample,
                    "sample_b": right_sample,
                    "group_a": left_group,
                    "group_b": right_group,
                    "pair_group": left_group if left_group == right_group else f"{left_group} vs {right_group}",
                    "relation": relation,
                    "distance": float(distance_matrix.loc[left_sample, right_sample]),
                }
            )
    return pd.DataFrame(rows)


def _build_within_between_boxplot(pair_df: pd.DataFrame, metric: str) -> go.Figure:
    colors = {"Within-group": "#5B8FF9", "Between-group": "#F6BD16"}
    fig = go.Figure()
    for relation in ("Within-group", "Between-group"):
        subset = pair_df.loc[pair_df["relation"] == relation].copy()
        if subset.empty:
            continue
        fig.add_trace(
            go.Box(
                x=subset["pair_group"],
                y=subset["distance"],
                name=relation,
                boxpoints="all",
                jitter=0.35,
                marker={"size": 5, "color": colors[relation]},
                line={"color": colors[relation]},
            )
        )
    fig.update_layout(
        title={"text": f"Within/Between Group Distances - {normalize_metric_title(metric)}", "x": 0.5},
        template="plotly_white",
        width=980,
        height=560,
        xaxis_title="Group pair",
        yaxis_title="Distance",
        boxmode="group",
    )
    return fig


def plot_beta_heatmaps(
    beta_dir: str = "work/06_final/beta",
    metadata_path: str | None = "work/00_input/metadata.txt",
    output_dir: str = DEFAULT_BETA_HEATMAP_DIR,
    metrics: list[str] | None = None,
    sample_id_col: str = "SampleID",
    group_col: str = "Group",
    permutations: int = 999,
    random_seed: int = 20260425,
    cluster_samples: bool = True,
    output_format: str = "html",
) -> dict[str, Any]:
    """Generate beta distance heatmaps and within/between group boxplots.

    Args:
        beta_dir: Directory containing beta distance matrices.
        metadata_path: Metadata TSV used for group colors and tests. If
            missing, groups are inferred from sample IDs.
        output_dir: Directory for generated plots and statistics.
        metrics: Metrics to process. Defaults to all matrix files found.
        sample_id_col: Metadata column containing sample IDs.
        group_col: Metadata column containing group labels.
        permutations: Permutation count for PERMANOVA/ANOSIM.
        random_seed: Random seed for fallback permutation tests.
        cluster_samples: Whether to cluster sample order in heatmaps.
        output_format: `html`, `png`, `pdf`, or `all`. Static formats require
            kaleido; HTML is always attempted.

    Returns:
        A dictionary describing generated files and skipped static exports.

    Raises:
        FileNotFoundError: If required input files are missing.
        ValueError: If matrices or metadata cannot be matched.
    """

    output_format = validate_output_format(output_format)
    if int(permutations) < 0:
        raise ValueError("permutations must be greater than or equal to 0.")

    resolved_output_dir = ensure_output_dir(output_dir)
    file_map = find_beta_distance_files(beta_dir, metrics=metrics)
    generated_files: list[str] = []
    skipped_static: list[str] = []
    heatmap_figures: dict[str, Any] = {}
    stat_rows: list[dict[str, Any]] = []
    pair_tables: list[pd.DataFrame] = []

    for metric, path in file_map.items():
        distance_matrix = read_distance_matrix(path, metric)
        sample_meta = build_sample_metadata(
            distance_matrix.index.tolist(),
            metadata_path=metadata_path,
            sample_id_col=sample_id_col,
            group_col=group_col,
        )
        groups = sample_meta["Group"].astype(str).tolist()
        permanova = _run_permanova(distance_matrix, groups, int(permutations), int(random_seed))
        anosim = _run_anosim(distance_matrix, groups, int(permutations), int(random_seed) + 17)
        stat_rows.append({"metric": metric, **permanova})
        stat_rows.append({"metric": metric, **anosim})

        heatmap = _build_beta_heatmap(
            distance_matrix,
            sample_meta,
            metric,
            cluster_samples=cluster_samples,
            permanova=permanova,
            anosim=anosim,
        )
        heatmap_figures[normalize_metric_title(metric)] = heatmap
        if output_format in {"html", "all"}:
            generated_files.append(
                write_html_figure(
                    heatmap,
                    os.path.join(resolved_output_dir, f"beta_heatmap_{metric}.html"),
                )
            )
        _write_optional_static(
            heatmap,
            os.path.join(resolved_output_dir, f"beta_heatmap_{metric}"),
            output_format,
            width=980,
            height=860,
            generated_files=generated_files,
            skipped_static=skipped_static,
        )

        pair_df = _within_between_distances(distance_matrix, sample_meta, metric)
        pair_tables.append(pair_df)
        boxplot = _build_within_between_boxplot(pair_df, metric)
        if output_format in {"html", "all"}:
            generated_files.append(
                write_html_figure(
                    boxplot,
                    os.path.join(resolved_output_dir, f"beta_within_between_boxplot_{metric}.html"),
                )
            )
        _write_optional_static(
            boxplot,
            os.path.join(resolved_output_dir, f"beta_within_between_boxplot_{metric}"),
            output_format,
            width=980,
            height=560,
            generated_files=generated_files,
            skipped_static=skipped_static,
        )

    stats_path = write_table(
        pd.DataFrame(stat_rows),
        os.path.join(resolved_output_dir, "beta_stat_results.tsv"),
        include_index=False,
    )
    pair_path = write_table(
        pd.concat(pair_tables, ignore_index=True),
        os.path.join(resolved_output_dir, "beta_within_between_distances.tsv"),
        include_index=False,
    )
    generated_files.insert(0, pair_path)
    generated_files.insert(0, stats_path)
    if output_format in {"html", "all"}:
        generated_files.append(
            write_html_dashboard(
                heatmap_figures,
                os.path.join(resolved_output_dir, "beta_heatmap_all_metrics.html"),
                "Beta Diversity Distance Heatmaps",
            )
        )

    return {
        "beta_dir": os.path.abspath(beta_dir),
        "metadata": None if metadata_path is None else os.path.abspath(metadata_path),
        "output_dir": resolved_output_dir,
        "metrics": list(file_map),
        "stats": stats_path,
        "pair_distances": pair_path,
        "plots": generated_files,
        "skipped_static_exports": skipped_static,
    }


TOOL_DEFINITIONS = [
    {
        "name": "plot_beta_pcoa",
        "description": (
            "Generate PCoA scatter plots from beta distance matrices in work/06_final/beta. "
            "Writes offline HTML plots and coordinate TSV files under work/06_final/plots by default."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "beta_dir": {"type": "string"},
                "metadata_path": {"type": "string"},
                "output_dir": {"type": "string", "default": DEFAULT_BETA_PCOA_DIR},
                "metrics": {"type": "array", "items": {"type": "string"}},
                "sample_id_col": {"type": "string", "default": "SampleID"},
                "group_col": {"type": "string", "default": "Group"},
                "show_labels": {"type": "boolean", "default": False},
                "ellipse_confidence": {"type": "number", "default": 0.95},
                "output_format": {
                    "type": "string",
                    "enum": ["html", "png", "pdf", "all"],
                    "default": "html",
                },
            },
        },
        "fn": plot_beta_pcoa,
    },
    {
        "name": "plot_beta_cpcoa",
        "description": (
            "Generate constrained PCoA plots from beta distance matrices and metadata groups. "
            "Writes offline HTML plots, coordinates, and pseudo-F statistics under work/06_final/plots."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "beta_dir": {"type": "string"},
                "metadata_path": {"type": "string"},
                "output_dir": {"type": "string", "default": DEFAULT_BETA_CPCOA_DIR},
                "metrics": {"type": "array", "items": {"type": "string"}},
                "sample_id_col": {"type": "string", "default": "SampleID"},
                "group_col": {"type": "string", "default": "Group"},
                "permutations": {"type": "integer", "default": 999},
                "random_seed": {"type": "integer", "default": 20260426},
                "show_labels": {"type": "boolean", "default": False},
                "ellipse_confidence": {"type": "number", "default": 0.68},
                "output_format": {
                    "type": "string",
                    "enum": ["html", "png", "pdf", "all"],
                    "default": "html",
                },
            },
        },
        "fn": plot_beta_cpcoa,
    },
    {
        "name": "plot_beta_heatmaps",
        "description": (
            "Generate beta distance heatmaps, PERMANOVA/ANOSIM summaries, and within/between group boxplots. "
            "Reads work/06_final/beta and writes outputs under work/06_final/plots by default."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "beta_dir": {"type": "string"},
                "metadata_path": {"type": "string"},
                "output_dir": {"type": "string", "default": DEFAULT_BETA_HEATMAP_DIR},
                "metrics": {"type": "array", "items": {"type": "string"}},
                "sample_id_col": {"type": "string", "default": "SampleID"},
                "group_col": {"type": "string", "default": "Group"},
                "permutations": {"type": "integer", "default": 999},
                "random_seed": {"type": "integer", "default": 20260425},
                "cluster_samples": {"type": "boolean", "default": True},
                "output_format": {
                    "type": "string",
                    "enum": ["html", "png", "pdf", "all"],
                    "default": "html",
                },
            },
        },
        "fn": plot_beta_heatmaps,
    },
]
