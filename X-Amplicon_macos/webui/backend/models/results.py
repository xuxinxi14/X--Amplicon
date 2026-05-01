"""Result-index models for completed X-Amplicon runs."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from webui.backend.models.common import WebUIBaseModel


class ResultFigure(WebUIBaseModel):
    """A discovered HTML/static figure."""

    label: str
    path: str
    category: str


class DifferentialComparisonResult(WebUIBaseModel):
    """Indexed files and counts for one differential comparison."""

    comparison: str
    result_path: str | None = None
    significant_path: str | None = None
    tested_features: int | None = None
    significant_features: int | None = None
    volcano: str | None = None
    heatmap: str | None = None


class ResultIndex(WebUIBaseModel):
    """Structured index for a project final output directory."""

    project_id: str
    final_dir: str
    available: bool
    messages: list[str] = Field(default_factory=list)
    summary_path: str | None = None
    provenance_json: str | None = None
    provenance_markdown: str | None = None
    plots_index: str | None = None
    report_html: str | None = None
    report_markdown: str | None = None
    report_data: str | None = None
    figures: dict[str, list[ResultFigure]] = Field(default_factory=dict)
    differential: list[DifferentialComparisonResult] = Field(default_factory=list)
    files: dict[str, Any] = Field(default_factory=dict)
