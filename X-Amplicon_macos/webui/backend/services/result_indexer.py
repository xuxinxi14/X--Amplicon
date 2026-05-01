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


def _html_figures(root: Path, category: str, pattern: str = "*.html") -> list[ResultFigure]:
    if not root.is_dir():
        return []
    figures: list[ResultFigure] = []
    for path in sorted(root.glob(pattern)):
        if path.is_file():
            figures.append(
                ResultFigure(
                    category=category,
                    label=path.stem.replace("_", " "),
                    path=str(path.resolve()),
                )
            )
    return figures


def _collect_plot_figures(plots_root: Path) -> dict[str, list[ResultFigure]]:
    return {
        "alpha": _html_figures(plots_root / "alpha_boxplot_chart", "alpha")
        + _html_figures(plots_root / "alpha_barplot_chart", "alpha")
        + _html_figures(plots_root / "alpha_rare_chart", "alpha"),
        "beta": _html_figures(plots_root / "beta_pcoa_chart", "beta")
        + _html_figures(plots_root / "beta_cpcoa_chart", "beta")
        + _html_figures(plots_root / "beta_heatmap_chart", "beta"),
        "taxonomy": _html_figures(plots_root / "taxonomy_stacked_bar_chart", "taxonomy")
        + _html_figures(plots_root / "taxonomy_heatmap_chart", "taxonomy"),
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
        comparisons.append(
            DifferentialComparisonResult(
                comparison=comparison,
                result_path=_exists(result_path),
                significant_path=_exists(significant_path),
                tested_features=_count_table_rows(result_path),
                significant_features=_count_table_rows(significant_path) or 0,
                volcano=_exists(root / "volcano_chart" / comparison / "volcano.html"),
                heatmap=_exists(root / "heatmap_chart" / comparison / "heatmap.html"),
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
