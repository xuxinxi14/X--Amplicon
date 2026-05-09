"""Taxonomy composition visualization tools for X-Amplicon outputs."""

from __future__ import annotations

try:
    import matplotlib
except ModuleNotFoundError:
    matplotlib = None
else:
    matplotlib.use("Agg")

import os
from typing import Any, Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .viz_common import (
    DEFAULT_TAXONOMY_LEVELS,
    DEFAULT_TAXONOMY_HEATMAP_DIR,
    DEFAULT_TAXONOMY_STACKED_BAR_DIR,
    apply_publication_theme,
    build_sample_metadata,
    ensure_output_dir,
    find_taxonomy_files,
    maybe_file,
    read_taxonomy_summary,
    resolve_color_palette,
    sort_groups,
    sort_sample_ids,
    sort_samples_by_metadata,
    validate_output_format,
    write_chart_index,
    write_html_dashboard,
    write_html_figure,
    write_optional_static,
    write_table,
)


def _resolve_levels(levels: Sequence[str] | None) -> list[str]:
    resolved = [str(level).strip().lower() for level in (levels or DEFAULT_TAXONOMY_LEVELS)]
    unknown = [level for level in resolved if level not in DEFAULT_TAXONOMY_LEVELS]
    if unknown:
        raise ValueError(
            f"Unknown taxonomy levels: {unknown}. Expected: {list(DEFAULT_TAXONOMY_LEVELS)}"
        )
    return list(dict.fromkeys(resolved))


def _sample_columns(table: pd.DataFrame) -> list[str]:
    return [column for column in table.columns if column != "Taxon"]


def _relative_abundance(table: pd.DataFrame, sample_columns: Sequence[str]) -> pd.DataFrame:
    values = table.loc[:, list(sample_columns)].astype(float)
    column_totals = values.sum(axis=0)
    relative = values.div(column_totals.replace(0, np.nan), axis=1).fillna(0.0) * 100.0
    return relative


def _filter_taxa(
    table: pd.DataFrame,
    sample_columns: Sequence[str],
    top_n: int | None,
    min_relative_abundance: float,
    include_others: bool = True,
) -> pd.DataFrame:
    relative = _relative_abundance(table, sample_columns)
    working = table.copy()
    working["_mean_relative"] = relative.mean(axis=1)
    working["_total"] = working.loc[:, list(sample_columns)].sum(axis=1)
    working = working.sort_values(["_mean_relative", "_total"], ascending=False, kind="stable")

    keep_mask = working["_mean_relative"] >= float(min_relative_abundance)
    if top_n is not None and int(top_n) > 0:
        rank_keep = pd.Series(False, index=working.index)
        rank_keep.iloc[: int(top_n)] = True
        keep_mask = keep_mask & rank_keep

    kept = working.loc[keep_mask].drop(columns=["_mean_relative", "_total"]).copy()
    dropped = working.loc[~keep_mask].drop(columns=["_mean_relative", "_total"]).copy()
    if include_others and not dropped.empty:
        others = {"Taxon": "Others"}
        for column in sample_columns:
            others[column] = float(dropped[column].sum())
        kept = pd.concat([kept, pd.DataFrame([others])], ignore_index=True)

    if kept.empty:
        raise ValueError("No taxa remain after filtering; lower min_relative_abundance or top_n.")
    return kept.reset_index(drop=True)


def _taxon_colors(
    taxa: Sequence[str],
    color_palette: str | Sequence[str] | dict[str, str] | None = None,
) -> dict[str, str]:
    colors = resolve_color_palette(
        taxa,
        color_palette=color_palette,
        default_mapping={"Others": "#B8C0CC"},
        sort_values=False,
    )
    if "Others" in colors:
        colors["Others"] = "#B8C0CC"
    return colors


def _build_stacked_bar(
    table: pd.DataFrame,
    sample_meta: pd.DataFrame,
    level: str,
    group_mean: bool,
    color_palette: str | Sequence[str] | dict[str, str] | None = None,
) -> go.Figure:
    sample_columns = _sample_columns(table)
    relative = _relative_abundance(table, sample_columns)
    long_table = table.loc[:, ["Taxon", *sample_columns]].melt(
        id_vars=["Taxon"],
        value_vars=sample_columns,
        var_name="SampleID",
        value_name="Abundance",
    )
    relative_long = relative.copy()
    relative_long.insert(0, "Taxon", table["Taxon"].tolist())
    relative_long = relative_long.melt(
        id_vars=["Taxon"],
        value_vars=sample_columns,
        var_name="SampleID",
        value_name="RelativeAbundance",
    )
    long_table = long_table.merge(relative_long, on=["Taxon", "SampleID"], how="left")
    long_table = long_table.merge(sample_meta, on="SampleID", how="left")

    if group_mean:
        plot_table = (
            long_table.groupby(["Taxon", "Group"], sort=False)[["Abundance", "RelativeAbundance"]]
            .mean()
            .reset_index()
            .rename(columns={"Group": "Category"})
        )
        x_values = sort_groups(plot_table["Category"].astype(str).tolist())
        title = f"Taxonomy Composition - {level.title()} Group Mean"
        x_title = "Group"
    else:
        plot_table = long_table.rename(columns={"SampleID": "Category"})
        x_values = sample_meta["SampleID"].astype(str).tolist()
        title = f"Taxonomy Composition - {level.title()}"
        x_title = "Sample"

    taxa = table["Taxon"].astype(str).tolist()
    colors = _taxon_colors(taxa, color_palette=color_palette)
    fig = go.Figure()
    for taxon in taxa:
        subset = plot_table.loc[plot_table["Taxon"] == taxon].copy()
        subset["Category"] = pd.Categorical(
            subset["Category"].astype(str),
            categories=x_values,
            ordered=True,
        )
        subset = subset.sort_values("Category")
        fig.add_trace(
            go.Bar(
                x=subset["Category"].astype(str),
                y=subset["RelativeAbundance"],
                name=str(taxon),
                marker_color=colors[str(taxon)],
                customdata=subset[["Abundance"]],
                hovertemplate=(
                    "%{x}<br>"
                    f"{level.title()}: {taxon}<br>"
                    "Relative abundance: %{y:.3f}%<br>"
                    "Value: %{customdata[0]:.4g}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title={"text": title, "x": 0.5},
        width=1100 if not group_mean else 820,
        height=680,
        barmode="stack",
        xaxis_title=x_title,
        yaxis_title="Relative abundance (%)",
        legend_title_text=level.title(),
        margin={"l": 70, "r": 220, "t": 80, "b": 120},
    )
    apply_publication_theme(fig, width=1100 if not group_mean else 820, height=680)
    fig.update_xaxes(tickangle=45 if not group_mean else 0)
    return fig


def plot_taxonomy_stacked_bars(
    taxonomy_summary_dir: str = "work/06_final/taxonomy_summary",
    metadata_path: str | None = "work/00_input/metadata.txt",
    output_dir: str = DEFAULT_TAXONOMY_STACKED_BAR_DIR,
    levels: list[str] | None = None,
    sample_id_col: str = "SampleID",
    group_col: str = "Group",
    top_n: int = 20,
    min_relative_abundance: float = 0.0,
    output_format: str = "html",
    include_others: bool = True,
    color_palette: str | list[str] | dict[str, str] | None = None,
) -> dict[str, Any]:
    """Generate taxonomy stacked bar charts for each taxonomy level.

    Args:
        taxonomy_summary_dir: Directory containing kingdom.tsv through
            species.tsv from the pipeline.
        metadata_path: Metadata TSV used for sample ordering and group means.
            If missing, groups are inferred from sample IDs.
        output_dir: Directory for generated plots and filtered tables.
        levels: Taxonomy levels to process. Defaults to all standard levels.
        sample_id_col: Metadata column containing sample IDs.
        group_col: Metadata column containing group labels.
        top_n: Keep the top N taxa per level. Use 0 to disable.
        min_relative_abundance: Minimum mean relative abundance percentage.
        output_format: `html`, `png`, `pdf`, `svg`, or `all`. Static formats require
            kaleido; HTML is always attempted.
        include_others: Whether to merge non-selected taxa into `Others`.
        color_palette: Optional comma-separated colors or `Taxon:#hex` pairs.

    Returns:
        A dictionary describing generated files and skipped static exports.

    Raises:
        FileNotFoundError: If required input directories or files are missing.
        ValueError: If taxonomy tables cannot be parsed.
    """

    output_format = validate_output_format(output_format)
    resolved_output_dir = ensure_output_dir(output_dir)
    resolved_levels = _resolve_levels(levels)
    file_map = find_taxonomy_files(taxonomy_summary_dir, levels=resolved_levels)
    generated_files: list[str] = []
    skipped_static: list[str] = []
    sample_figures: dict[str, Any] = {}
    group_figures: dict[str, Any] = {}
    filtered_tables: dict[str, str] = {}

    for level, path in file_map.items():
        table = read_taxonomy_summary(path, level)
        raw_sample_columns = _sample_columns(table)
        sample_meta = build_sample_metadata(
            raw_sample_columns,
            metadata_path=metadata_path,
            sample_id_col=sample_id_col,
            group_col=group_col,
        )
        sample_columns = sort_samples_by_metadata(raw_sample_columns, sample_meta)
        sample_meta = (
            sample_meta.set_index("SampleID", drop=False)
            .loc[sample_columns, ["SampleID", "Group"]]
            .reset_index(drop=True)
        )
        table = table.loc[:, ["Taxon", *sample_columns]].copy()
        filtered = _filter_taxa(
            table,
            sample_columns,
            None if int(top_n) <= 0 else int(top_n),
            min_relative_abundance=float(min_relative_abundance),
            include_others=bool(include_others),
        )
        filtered_path = write_table(
            filtered,
            os.path.join(resolved_output_dir, f"taxonomy_stacked_bar_{level}_filtered.tsv"),
            include_index=False,
        )
        filtered_tables[level] = filtered_path
        generated_files.append(filtered_path)
        sample_fig = _build_stacked_bar(
            filtered,
            sample_meta,
            level,
            group_mean=False,
            color_palette=color_palette,
        )
        group_fig = _build_stacked_bar(
            filtered,
            sample_meta,
            level,
            group_mean=True,
            color_palette=color_palette,
        )
        sample_figures[level.title()] = sample_fig
        group_figures[f"{level.title()} Group Mean"] = group_fig

        if output_format in {"html", "all"}:
            generated_files.append(
                write_html_figure(
                    sample_fig,
                    os.path.join(resolved_output_dir, f"taxonomy_stacked_bar_{level}.html"),
                )
            )
            generated_files.append(
                write_html_figure(
                    group_fig,
                    os.path.join(resolved_output_dir, f"taxonomy_group_mean_stacked_bar_{level}.html"),
                )
            )
        write_optional_static(
            sample_fig,
            os.path.join(resolved_output_dir, f"taxonomy_stacked_bar_{level}"),
            output_format,
            width=1100,
            height=680,
            generated_files=generated_files,
            skipped_static=skipped_static,
        )
        write_optional_static(
            group_fig,
            os.path.join(resolved_output_dir, f"taxonomy_group_mean_stacked_bar_{level}"),
            output_format,
            width=820,
            height=680,
            generated_files=generated_files,
            skipped_static=skipped_static,
        )

    if output_format in {"html", "all"} and sample_figures:
        generated_files.append(
            write_html_dashboard(
                sample_figures,
                os.path.join(resolved_output_dir, "taxonomy_stacked_bar_report.html"),
                "Taxonomy Composition Stacked Bars",
            )
        )
        generated_files.append(
            write_html_dashboard(
                group_figures,
                os.path.join(resolved_output_dir, "taxonomy_group_mean_stacked_bar_report.html"),
                "Taxonomy Composition Group Mean",
            )
        )
    generated_files.append(
        write_chart_index(
            resolved_output_dir,
            "Taxonomy Composition Stacked Bars",
            generated_files,
            "Sample-level and group-mean stacked bars with top taxa and optional Others merging.",
        )
    )

    return {
        "taxonomy_summary_dir": os.path.abspath(taxonomy_summary_dir),
        "metadata": None if metadata_path is None else os.path.abspath(metadata_path),
        "output_dir": resolved_output_dir,
        "levels": list(file_map),
        "filtered_tables": filtered_tables,
        "plots": generated_files,
        "skipped_static_exports": skipped_static,
    }


def _normalize_heatmap_matrix(matrix: pd.DataFrame, normalization: str) -> pd.DataFrame:
    method = str(normalization).strip().lower()
    if method == "none":
        return matrix.copy()
    if method == "minmax":
        row_min = matrix.min(axis=1)
        row_max = matrix.max(axis=1)
        return matrix.sub(row_min, axis=0).div((row_max - row_min).replace(0, np.nan), axis=0).fillna(0.0)
    if method == "zscore":
        row_mean = matrix.mean(axis=1)
        row_std = matrix.std(axis=1, ddof=1).replace(0, np.nan)
        return matrix.sub(row_mean, axis=0).div(row_std, axis=0).fillna(0.0)
    raise ValueError("normalization must be one of: none, minmax, zscore.")


def _build_taxonomy_heatmap(
    normalized_matrix: pd.DataFrame,
    relative_matrix: pd.DataFrame,
    level: str,
    normalization: str,
) -> go.Figure:
    taxa = normalized_matrix.index.astype(str).tolist()
    samples = normalized_matrix.columns.astype(str).tolist()
    customdata = np.empty((len(taxa), len(samples), 2), dtype=object)
    for row_index, taxon in enumerate(taxa):
        for col_index, sample in enumerate(samples):
            customdata[row_index, col_index] = [
                taxon,
                float(relative_matrix.iloc[row_index, col_index]),
            ]

    zmin = float(np.nanmin(normalized_matrix.to_numpy(dtype=float)))
    zmax = float(np.nanmax(normalized_matrix.to_numpy(dtype=float)))
    heatmap_kwargs: dict[str, Any] = {
        "z": normalized_matrix.to_numpy(dtype=float),
        "x": samples,
        "y": taxa,
        "colorscale": "RdBu_r" if zmin < 0 < zmax else "YlOrRd",
        "customdata": customdata,
        "colorbar": {"title": normalization},
        "hovertemplate": (
            f"{level.title()}: %{{customdata[0]}}<br>"
            "Sample: %{x}<br>"
            "Relative abundance: %{customdata[1]:.4f}%<br>"
            "Displayed value: %{z:.4f}<extra></extra>"
        ),
    }
    if zmin < 0 < zmax:
        heatmap_kwargs["zmid"] = 0

    fig = go.Figure(data=go.Heatmap(**heatmap_kwargs))
    fig.update_layout(
        title={"text": f"Taxonomy Heatmap - {level.title()} ({normalization})", "x": 0.5},
        width=1100,
        height=max(520, min(1800, 240 + len(taxa) * 18)),
        xaxis_title="Sample",
        yaxis_title=level.title(),
        margin={"l": min(360, 100 + max((len(taxon) for taxon in taxa), default=0) * 5), "r": 100, "t": 80, "b": 100},
    )
    apply_publication_theme(fig, width=1100, height=int(fig.layout.height or 800))
    fig.update_xaxes(tickangle=45)
    fig.update_yaxes(autorange="reversed")
    return fig


def plot_taxonomy_heatmaps(
    taxonomy_summary_dir: str = "work/06_final/taxonomy_summary",
    metadata_path: str | None = "work/00_input/metadata.txt",
    output_dir: str = DEFAULT_TAXONOMY_HEATMAP_DIR,
    levels: list[str] | None = None,
    sample_id_col: str = "SampleID",
    group_col: str = "Group",
    top_n: int = 80,
    min_mean_relative_abundance: float = 0.001,
    normalization: str = "zscore",
    output_format: str = "html",
    include_others: bool = True,
) -> dict[str, Any]:
    """Generate taxonomy abundance heatmaps for each taxonomy level.

    Args:
        taxonomy_summary_dir: Directory containing kingdom.tsv through
            species.tsv from the pipeline.
        metadata_path: Optional metadata TSV used for sample ordering.
        output_dir: Directory for generated plots and heatmap matrices.
        levels: Taxonomy levels to process. Defaults to all standard levels.
        sample_id_col: Metadata column containing sample IDs.
        group_col: Metadata column containing group labels.
        top_n: Keep the top N taxa per level. Use 0 to disable.
        min_mean_relative_abundance: Minimum mean relative abundance percentage.
        normalization: Heatmap normalization: `none`, `minmax`, or `zscore`.
        output_format: `html`, `png`, `pdf`, `svg`, or `all`. Static formats require
            kaleido; HTML is always attempted.
        include_others: Whether to merge non-selected taxa into `Others`.

    Returns:
        A dictionary describing generated files and skipped static exports.

    Raises:
        FileNotFoundError: If required input directories or files are missing.
        ValueError: If taxonomy tables cannot be parsed.
    """

    output_format = validate_output_format(output_format)
    resolved_output_dir = ensure_output_dir(output_dir)
    resolved_metadata_path = maybe_file(metadata_path)
    resolved_levels = _resolve_levels(levels)
    file_map = find_taxonomy_files(taxonomy_summary_dir, levels=resolved_levels)
    generated_files: list[str] = []
    skipped_static: list[str] = []
    figures: dict[str, Any] = {}
    matrix_tables: dict[str, dict[str, str]] = {}

    for level, path in file_map.items():
        table = read_taxonomy_summary(path, level)
        raw_sample_columns = _sample_columns(table)
        if resolved_metadata_path is not None:
            sample_meta = build_sample_metadata(
                raw_sample_columns,
                metadata_path=resolved_metadata_path,
                sample_id_col=sample_id_col,
                group_col=group_col,
            )
            sample_columns = sort_samples_by_metadata(raw_sample_columns, sample_meta)
        else:
            sample_columns = sort_sample_ids(raw_sample_columns)
        table = table.loc[:, ["Taxon", *sample_columns]].copy()
        filtered = _filter_taxa(
            table,
            sample_columns,
            None if int(top_n) <= 0 else int(top_n),
            min_relative_abundance=float(min_mean_relative_abundance),
            include_others=bool(include_others),
        )
        relative = _relative_abundance(filtered, sample_columns)
        relative.index = filtered["Taxon"].astype(str)
        normalized = _normalize_heatmap_matrix(relative, normalization)

        relative_table = relative.copy()
        relative_table.insert(0, "Taxon", relative_table.index)
        normalized_table = normalized.copy()
        normalized_table.insert(0, "Taxon", normalized_table.index)
        relative_path = write_table(
            relative_table,
            os.path.join(resolved_output_dir, f"taxonomy_heatmap_{level}_filtered_relative.tsv"),
            include_index=False,
        )
        normalized_path = write_table(
            normalized_table,
            os.path.join(resolved_output_dir, f"taxonomy_heatmap_{level}_normalized.tsv"),
            include_index=False,
        )
        generated_files.extend([relative_path, normalized_path])
        matrix_tables[level] = {
            "relative": relative_path,
            "normalized": normalized_path,
        }

        fig = _build_taxonomy_heatmap(normalized, relative, level, normalization)
        figures[level.title()] = fig
        if output_format in {"html", "all"}:
            generated_files.append(
                write_html_figure(
                    fig,
                    os.path.join(resolved_output_dir, f"taxonomy_heatmap_{level}.html"),
                )
            )
        write_optional_static(
            fig,
            os.path.join(resolved_output_dir, f"taxonomy_heatmap_{level}"),
            output_format,
            width=1100,
            height=int(fig.layout.height or 800),
            generated_files=generated_files,
            skipped_static=skipped_static,
        )

    if output_format in {"html", "all"} and figures:
        generated_files.append(
            write_html_dashboard(
                figures,
                os.path.join(resolved_output_dir, "taxonomy_heatmap_report.html"),
                "Taxonomy Heatmaps",
            )
        )
    generated_files.append(
        write_chart_index(
            resolved_output_dir,
            "Taxonomy Heatmaps",
            generated_files,
            "Taxonomy abundance heatmaps with top taxa and optional Others merging.",
        )
    )

    return {
        "taxonomy_summary_dir": os.path.abspath(taxonomy_summary_dir),
        "metadata": resolved_metadata_path,
        "output_dir": resolved_output_dir,
        "levels": list(file_map),
        "matrix_tables": matrix_tables,
        "plots": generated_files,
        "skipped_static_exports": skipped_static,
    }


TOOL_DEFINITIONS = [
    {
        "name": "plot_taxonomy_stacked_bars",
        "description": (
            "Generate taxonomy composition stacked bar charts from work/06_final/taxonomy_summary. "
            "Writes offline HTML plots and filtered tables under work/06_final/plots by default."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "taxonomy_summary_dir": {"type": "string"},
                "metadata_path": {"type": "string"},
                "output_dir": {"type": "string", "default": DEFAULT_TAXONOMY_STACKED_BAR_DIR},
                "levels": {"type": "array", "items": {"type": "string"}},
                "sample_id_col": {"type": "string", "default": "SampleID"},
                "group_col": {"type": "string", "default": "Group"},
                "top_n": {"type": "integer", "default": 20},
                "min_relative_abundance": {"type": "number", "default": 0.0},
                "output_format": {
                    "type": "string",
                    "enum": ["html", "png", "pdf", "svg", "all"],
                    "default": "html",
                },
                "include_others": {"type": "boolean", "default": True},
                "color_palette": {
                    "type": "string",
                    "description": "Optional comma-separated colors or Taxon:#hex pairs.",
                },
            },
        },
        "fn": plot_taxonomy_stacked_bars,
    },
    {
        "name": "plot_taxonomy_heatmaps",
        "description": (
            "Generate taxonomy abundance heatmaps from work/06_final/taxonomy_summary. "
            "Writes offline HTML heatmaps and plotted matrices under work/06_final/plots by default."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "taxonomy_summary_dir": {"type": "string"},
                "metadata_path": {"type": "string"},
                "output_dir": {"type": "string", "default": DEFAULT_TAXONOMY_HEATMAP_DIR},
                "levels": {"type": "array", "items": {"type": "string"}},
                "sample_id_col": {"type": "string", "default": "SampleID"},
                "group_col": {"type": "string", "default": "Group"},
                "top_n": {"type": "integer", "default": 80},
                "min_mean_relative_abundance": {"type": "number", "default": 0.001},
                "normalization": {
                    "type": "string",
                    "enum": ["none", "minmax", "zscore"],
                    "default": "zscore",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["html", "png", "pdf", "svg", "all"],
                    "default": "html",
                },
                "include_others": {"type": "boolean", "default": True},
            },
        },
        "fn": plot_taxonomy_heatmaps,
    },
]
