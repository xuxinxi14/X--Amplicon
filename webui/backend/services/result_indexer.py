"""Index completed X-Amplicon outputs for Web UI result browsing."""

from __future__ import annotations

from pathlib import Path

from webui.backend.config import resolve_path
from webui.backend.models.project import ProjectRecord
from webui.backend.models.results import (
    DifferentialComparisonResult,
    ResultFigure,
    ResultIndex,
)

FIGURE_FORMATS = ("html", "png", "svg", "pdf")


def _exists(path: Path) -> str | None:
    return str(path.resolve()) if path.is_file() else None


def _count_table_rows(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            count = sum(1 for _ in handle)
    except OSError:
        return None
    return max(0, count - 1)


def _preferred_figure_path(formats: dict[str, str]) -> str | None:
    for suffix in FIGURE_FORMATS:
        if suffix in formats:
            return formats[suffix]
    return None


def _figure_formats(root: Path, stem: str) -> dict[str, str]:
    formats: dict[str, str] = {}
    for suffix in FIGURE_FORMATS:
        path = root / f"{stem}.{suffix}"
        if path.is_file():
            formats[suffix] = str(path.resolve())
    return formats


def _figures(root: Path, category: str) -> list[ResultFigure]:
    if not root.is_dir():
        return []
    stems = sorted({path.stem for path in root.iterdir() if path.is_file() and path.suffix.lower().lstrip(".") in FIGURE_FORMATS})
    figures = []
    for stem in stems:
        formats = _figure_formats(root, stem)
        preferred = _preferred_figure_path(formats)
        if preferred:
            figures.append(
                ResultFigure(
                    category=category,
                    label=stem.replace("_", " "),
                    path=preferred,
                    formats=formats,
                )
            )
    return figures


def _collect_plot_figures(plots_root: Path) -> dict[str, list[ResultFigure]]:
    return {
        "alpha": _figures(plots_root / "alpha_boxplot_chart", "alpha")
        + _figures(plots_root / "alpha_barplot_chart", "alpha")
        + _figures(plots_root / "alpha_rare_chart", "alpha"),
        "beta": _figures(plots_root / "beta_pcoa_chart", "beta")
        + _figures(plots_root / "beta_cpcoa_chart", "beta")
        + _figures(plots_root / "beta_heatmap_chart", "beta"),
        "taxonomy": _figures(plots_root / "taxonomy_stacked_bar_chart", "taxonomy")
        + _figures(plots_root / "taxonomy_heatmap_chart", "taxonomy"),
    }


def _collect_differential(final_dir: Path) -> list[DifferentialComparisonResult]:
    root = final_dir / "statistics" / "differential"
    result_root = root / "comparison_result"
    comparisons: list[DifferentialComparisonResult] = []
    if not result_root.is_dir():
        return comparisons
    for comparison_dir in sorted(path for path in result_root.iterdir() if path.is_dir()):
        comparison = comparison_dir.name
        result_path = comparison_dir / "differential_results.tsv"
        significant_path = comparison_dir / "differential_results_significant.tsv"
        volcano_formats = _figure_formats(root / "volcano_chart" / comparison, "volcano")
        heatmap_formats = _figure_formats(root / "heatmap_chart" / comparison, "heatmap")
        comparisons.append(
            DifferentialComparisonResult(
                comparison=comparison,
                result_path=_exists(result_path),
                significant_path=_exists(significant_path),
                tested_features=_count_table_rows(result_path),
                significant_features=_count_table_rows(significant_path) or 0,
                volcano=_preferred_figure_path(volcano_formats),
                heatmap=_preferred_figure_path(heatmap_formats),
                volcano_formats=volcano_formats,
                heatmap_formats=heatmap_formats,
            )
        )
    return comparisons


def _file_summary(final_dir: Path) -> dict[str, str | None]:
    return {
        "otutab": _exists(final_dir / "otutab.txt"),
        "taxonomy": _exists(final_dir / "taxonomy.tsv"),
        "alpha_diversity": _exists(final_dir / "alpha_diversity.txt")
        or _exists(final_dir / "alpha" / "alpha_diversity.tsv"),
        "rarefied_otutab": _exists(final_dir / "otutab_rare.txt"),
        "plot_index": _exists(final_dir / "plots" / "index.html"),
    }


def final_dir_for_project(project: ProjectRecord) -> Path:
    """Return the standard 06_final directory for a project."""

    output_root = resolve_path(project.output_root, project.project_dir)
    return output_root / "06_final"


def build_result_index(project: ProjectRecord) -> ResultIndex:
    """Index a project's final outputs."""

    final_dir = final_dir_for_project(project)
    plots_root = final_dir / "plots"
    available = final_dir.is_dir()
    messages: list[str] = []
    if not available:
        messages.append("Final output directory was not found. Run the pipeline before browsing results.")

    figures = _collect_plot_figures(plots_root) if available else {}
    differential = _collect_differential(final_dir) if available else []
    report_dir = final_dir / "report"
    return ResultIndex(
        project_id=project.id,
        final_dir=str(final_dir.resolve()),
        available=available,
        messages=messages,
        summary_path=_exists(final_dir / "run_summary.json"),
        provenance_json=_exists(final_dir / "provenance.json"),
        provenance_markdown=_exists(final_dir / "provenance.md"),
        plots_index=_exists(plots_root / "index.html"),
        report_html=_exists(report_dir / "analysis_report.html"),
        report_markdown=_exists(report_dir / "analysis_report.md"),
        report_data=_exists(report_dir / "report_data.json") or _exists(report_dir / "analysis_report_data.json"),
        figures=figures,
        differential=differential,
        files=_file_summary(final_dir) if available else {},
    )
