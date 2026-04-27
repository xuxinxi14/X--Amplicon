"""Batch visualization entry point for completed X-Amplicon runs."""

from __future__ import annotations

try:
    import matplotlib
except ModuleNotFoundError:
    matplotlib = None
else:
    matplotlib.use("Agg")

import os
from typing import Any

from .viz_alpha_diversity import (
    plot_alpha_barplots,
    plot_alpha_boxplots,
    plot_alpha_rarefaction_curve,
)
from .viz_beta_diversity import plot_beta_cpcoa, plot_beta_heatmaps, plot_beta_pcoa
from .viz_common import (
    DEFAULT_FINAL_DIR,
    DEFAULT_PLOTS_DIR,
    ensure_output_dir,
    maybe_file,
    validate_output_format,
    write_chart_index,
)
from .viz_taxonomy import plot_taxonomy_heatmaps, plot_taxonomy_stacked_bars

VISUALIZATION_OUTPUT_SUBDIRS = {
    "alpha_boxplots": "alpha_boxplot_chart",
    "alpha_barplots": "alpha_barplot_chart",
    "alpha_rarefaction": "alpha_rare_chart",
    "beta_pcoa": "beta_pcoa_chart",
    "beta_cpcoa": "beta_cpcoa_chart",
    "beta_heatmaps": "beta_heatmap_chart",
    "taxonomy_stacked_bars": "taxonomy_stacked_bar_chart",
    "taxonomy_heatmaps": "taxonomy_heatmap_chart",
}


def _default_metadata_path(final_dir: str, metadata_path: str | None) -> str | None:
    if maybe_file(metadata_path) is not None:
        return os.path.abspath(str(metadata_path))

    final_dir = os.path.abspath(final_dir)
    work_root = os.path.dirname(final_dir)
    candidates = [
        os.path.join(work_root, "00_input", "metadata.txt"),
        os.path.join(os.getcwd(), "metadata.txt"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def _output_subdir(output_root: str, key: str) -> str:
    """Resolve and create the output subdirectory for one visualization family."""

    subdir_name = VISUALIZATION_OUTPUT_SUBDIRS[key]
    return ensure_output_dir(os.path.join(output_root, subdir_name))


def run_visualization_suite(
    final_dir: str = DEFAULT_FINAL_DIR,
    metadata_path: str | None = None,
    output_dir: str | None = None,
    output_format: str = "html",
    sample_id_col: str = "SampleID",
    group_col: str = "Group",
    beta_metrics: list[str] | None = None,
    taxonomy_levels: list[str] | None = None,
    include_cpcoa: bool = True,
    include_beta_stats: bool = True,
    include_taxonomy_heatmaps: bool = True,
    include_taxonomy_stacked_bars: bool = True,
    color_palette: str | list[str] | dict[str, str] | None = None,
) -> dict[str, Any]:
    """Generate the standard visualization set for a completed pipeline run.

    Args:
        final_dir: Pipeline final output directory, usually `work/06_final`.
        metadata_path: Optional metadata file. If omitted, the function tries
            `work/00_input/metadata.txt` and then repository `metadata.txt`.
        output_dir: Plot output root. Defaults to `<final_dir>/plots`, with
            one subdirectory per visualization family.
        output_format: `html`, `png`, `pdf`, `svg`, or `all`. Static formats require
            kaleido; HTML is always attempted.
        sample_id_col: Metadata column containing sample IDs.
        group_col: Metadata column containing group labels.
        beta_metrics: Optional beta distance metrics to plot.
        taxonomy_levels: Optional taxonomy levels to plot.
        include_cpcoa: Whether to generate constrained PCoA plots.
        include_beta_stats: Whether to generate beta heatmaps and group tests.
        include_taxonomy_heatmaps: Whether to generate taxonomy heatmaps.
        include_taxonomy_stacked_bars: Whether to generate taxonomy stacked bars.
        color_palette: Optional comma-separated colors or `Group:#hex` pairs.

    Returns:
        A dictionary with one key per visualization family and a flattened list
        of generated files.

    Raises:
        FileNotFoundError: If required completed-run inputs are missing.
        ValueError: If an input table cannot be parsed or matched to metadata.
    """

    output_format = validate_output_format(output_format)
    resolved_final_dir = os.path.abspath(final_dir)
    if not os.path.isdir(resolved_final_dir):
        raise FileNotFoundError(f"final_dir not found: {resolved_final_dir}")

    resolved_output_dir = ensure_output_dir(output_dir or os.path.join(resolved_final_dir, "plots"))
    resolved_metadata_path = _default_metadata_path(resolved_final_dir, metadata_path)

    alpha_diversity_path = os.path.join(resolved_final_dir, "alpha", "alpha_diversity.tsv")
    alpha_rarefaction_path = os.path.join(resolved_final_dir, "alpha", "alpha_rarefaction.tsv")
    beta_dir = os.path.join(resolved_final_dir, "beta")
    taxonomy_summary_dir = os.path.join(resolved_final_dir, "taxonomy_summary")

    results: dict[str, Any] = {
        "final_dir": resolved_final_dir,
        "metadata": resolved_metadata_path,
        "output_dir": resolved_output_dir,
        "output_subdirs": {
            key: os.path.join(resolved_output_dir, subdir)
            for key, subdir in VISUALIZATION_OUTPUT_SUBDIRS.items()
        },
        "output_format": output_format,
        "color_palette": color_palette,
    }

    results["alpha_boxplots"] = plot_alpha_boxplots(
        alpha_diversity_path=alpha_diversity_path,
        metadata_path=resolved_metadata_path,
        output_dir=_output_subdir(resolved_output_dir, "alpha_boxplots"),
        sample_id_col=sample_id_col,
        group_col=group_col,
        output_format=output_format,
        color_palette=color_palette,
    )
    results["alpha_barplots"] = plot_alpha_barplots(
        alpha_diversity_path=alpha_diversity_path,
        metadata_path=resolved_metadata_path,
        output_dir=_output_subdir(resolved_output_dir, "alpha_barplots"),
        sample_id_col=sample_id_col,
        group_col=group_col,
        output_format=output_format,
        color_palette=color_palette,
    )
    results["alpha_rarefaction"] = plot_alpha_rarefaction_curve(
        alpha_rarefaction_path=alpha_rarefaction_path,
        metadata_path=resolved_metadata_path,
        output_dir=_output_subdir(resolved_output_dir, "alpha_rarefaction"),
        sample_id_col=sample_id_col,
        group_col=group_col,
        output_format=output_format,
        color_palette=color_palette,
    )
    results["beta_pcoa"] = plot_beta_pcoa(
        beta_dir=beta_dir,
        metadata_path=resolved_metadata_path,
        output_dir=_output_subdir(resolved_output_dir, "beta_pcoa"),
        metrics=beta_metrics,
        sample_id_col=sample_id_col,
        group_col=group_col,
        output_format=output_format,
        color_palette=color_palette,
    )

    if include_cpcoa:
        results["beta_cpcoa"] = plot_beta_cpcoa(
            beta_dir=beta_dir,
            metadata_path=resolved_metadata_path,
            output_dir=_output_subdir(resolved_output_dir, "beta_cpcoa"),
            metrics=beta_metrics,
            sample_id_col=sample_id_col,
            group_col=group_col,
            output_format=output_format,
            color_palette=color_palette,
        )
    if include_beta_stats:
        results["beta_heatmaps"] = plot_beta_heatmaps(
            beta_dir=beta_dir,
            metadata_path=resolved_metadata_path,
            output_dir=_output_subdir(resolved_output_dir, "beta_heatmaps"),
            metrics=beta_metrics,
            sample_id_col=sample_id_col,
            group_col=group_col,
            output_format=output_format,
            color_palette=color_palette,
        )
    if include_taxonomy_stacked_bars:
        results["taxonomy_stacked_bars"] = plot_taxonomy_stacked_bars(
            taxonomy_summary_dir=taxonomy_summary_dir,
            metadata_path=resolved_metadata_path,
            output_dir=_output_subdir(resolved_output_dir, "taxonomy_stacked_bars"),
            levels=taxonomy_levels,
            sample_id_col=sample_id_col,
            group_col=group_col,
            output_format=output_format,
            color_palette=color_palette,
        )
    if include_taxonomy_heatmaps:
        results["taxonomy_heatmaps"] = plot_taxonomy_heatmaps(
            taxonomy_summary_dir=taxonomy_summary_dir,
            metadata_path=resolved_metadata_path,
            output_dir=_output_subdir(resolved_output_dir, "taxonomy_heatmaps"),
            levels=taxonomy_levels,
            sample_id_col=sample_id_col,
            group_col=group_col,
            output_format=output_format,
        )

    generated_files: list[str] = []
    skipped_static_exports: list[str] = []
    for value in results.values():
        if not isinstance(value, dict):
            continue
        plots = value.get("plots")
        if isinstance(plots, list):
            generated_files.extend(str(path) for path in plots)
        skipped = value.get("skipped_static_exports")
        if isinstance(skipped, list):
            skipped_static_exports.extend(str(path) for path in skipped)

    deduped_files: list[str] = []
    seen: set[str] = set()
    for path in generated_files:
        if path not in seen:
            seen.add(path)
            deduped_files.append(path)

    index_path = write_chart_index(
        resolved_output_dir,
        "X-Amplicon Visualization Index",
        deduped_files,
        "Publication-ready alpha, beta, and taxonomy visualization outputs.",
    )
    if index_path not in seen:
        deduped_files.append(index_path)

    results["index"] = index_path
    results["generated_files"] = deduped_files
    results["skipped_static_exports"] = skipped_static_exports
    return results


TOOL_DEFINITIONS = [
    {
        "name": "run_visualization_suite",
        "description": (
            "Generate publication-ready alpha, beta, and taxonomy visualizations for a completed "
            "X-Amplicon run. Reads work/06_final by default and writes charts to "
            "organized subdirectories under work/06_final/plots."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "final_dir": {"type": "string", "default": DEFAULT_FINAL_DIR},
                "metadata_path": {"type": "string"},
                "output_dir": {"type": "string", "default": DEFAULT_PLOTS_DIR},
                "output_format": {
                    "type": "string",
                    "enum": ["html", "png", "pdf", "svg", "all"],
                    "default": "html",
                },
                "sample_id_col": {"type": "string", "default": "SampleID"},
                "group_col": {"type": "string", "default": "Group"},
                "beta_metrics": {"type": "array", "items": {"type": "string"}},
                "taxonomy_levels": {"type": "array", "items": {"type": "string"}},
                "include_cpcoa": {"type": "boolean", "default": True},
                "include_beta_stats": {"type": "boolean", "default": True},
                "include_taxonomy_heatmaps": {"type": "boolean", "default": True},
                "include_taxonomy_stacked_bars": {"type": "boolean", "default": True},
                "color_palette": {
                    "type": "string",
                    "description": "Optional comma-separated colors or Group:#hex pairs.",
                },
            },
        },
        "fn": run_visualization_suite,
    }
]
