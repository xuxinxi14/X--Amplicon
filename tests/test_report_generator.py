"""Tests for the X-Amplicon analysis report generator."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pandas as pd
from click.testing import CliRunner

from agent.tools import get_tool_schemas
from process import cli
from src.core.report_generator import generate_analysis_report


def _make_completed_run(temp_path: Path) -> Path:
    work_dir = temp_path / "work"
    final_dir = work_dir / "06_final"
    input_dir = work_dir / "00_input"
    alpha_dir = final_dir / "alpha"
    beta_dir = final_dir / "beta"
    taxonomy_dir = final_dir / "taxonomy_summary"
    plots_dir = final_dir / "plots"
    for directory in (input_dir, alpha_dir, beta_dir, taxonomy_dir, plots_dir / "alpha_boxplot_chart"):
        directory.mkdir(parents=True, exist_ok=True)

    metadata_path = input_dir / "metadata.txt"
    pd.DataFrame({"SampleID": ["S1", "S2", "S3"], "Group": ["A", "A", "B"]}).to_csv(
        metadata_path,
        sep="\t",
        index=False,
    )
    otutab_path = final_dir / "otutab.txt"
    pd.DataFrame(
        {"S1": [10, 0], "S2": [6, 4], "S3": [2, 8]},
        index=["OTU1", "OTU2"],
    ).to_csv(otutab_path, sep="\t")
    pd.DataFrame(
        {
            "SampleID": ["S1", "S2", "S3"],
            "Observed_OTUs": [10, 12, 8],
            "Shannon": [1.1, 1.3, 0.9],
            "Simpson": [0.7, 0.8, 0.6],
            "Chao1": [11.0, 13.0, 9.0],
            "ACE": [11.5, 13.5, 9.5],
        }
    ).to_csv(alpha_dir / "alpha_diversity.tsv", sep="\t", index=False)
    pd.DataFrame(
        [[0.0, 0.2, 0.4], [0.2, 0.0, 0.3], [0.4, 0.3, 0.0]],
        index=["S1", "S2", "S3"],
        columns=["S1", "S2", "S3"],
    ).to_csv(beta_dir / "braycurtis.tsv", sep="\t", index_label="SampleID")
    pd.DataFrame(
        {
            "Phylum": ["Firmicutes", "Proteobacteria"],
            "S1": [60.0, 40.0],
            "S2": [55.0, 45.0],
            "S3": [25.0, 75.0],
        }
    ).to_csv(taxonomy_dir / "phylum.tsv", sep="\t", index=False)
    (plots_dir / "index.html").write_text("<html>plots</html>", encoding="utf-8")
    (plots_dir / "alpha_boxplot_chart" / "alpha_boxplots.html").write_text(
        "<html>alpha</html>",
        encoding="utf-8",
    )

    summary = {
        "status": "success",
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:01:00+00:00",
        "sample_ids": ["S1", "S2", "S3"],
        "effective_params": {
            "feature_method": "usearch-asv",
            "otutab_method": "usearch",
            "annotation_database": "rdp_16s_v18",
            "filter_route": "16s",
            "rarefaction_depth": 1000,
        },
        "outputs": {
            "metadata": str(metadata_path),
            "final_outputs": {
                "feature_table": str(otutab_path),
                "kept_features": 2,
                "route": "16s",
            },
            "analysis_outputs": {
                "alpha_diversity": str(alpha_dir / "alpha_diversity.tsv"),
                "beta_matrices": {"braycurtis": str(beta_dir / "braycurtis.tsv")},
                "taxonomy_summaries": {"Phylum": str(taxonomy_dir / "phylum.tsv")},
            },
        },
        "steps": [
            {
                "name": "validate_inputs",
                "status": "completed",
                "started_at": "2026-01-01T00:00:00+00:00",
                "completed_at": "2026-01-01T00:00:01+00:00",
                "description": "Validate inputs.",
            }
        ],
    }
    summary_path = final_dir / "run_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    provenance = {
        "project": {"commit": "abc123", "branch": "main", "dirty": False},
        "runtime": {"python_version": "3.13"},
        "tools": {},
        "databases": {},
    }
    (final_dir / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return final_dir


class ReportGeneratorTests(unittest.TestCase):
    def test_generate_analysis_report_writes_markdown_html_and_data(self) -> None:
        temp_path = Path("tests") / f"tmp_report_{uuid4().hex}"
        try:
            final_dir = _make_completed_run(temp_path)

            result = generate_analysis_report(final_dir=str(final_dir))

            markdown = Path(result["markdown"])
            html = Path(result["html"])
            data = Path(result["data"])
            self.assertTrue(markdown.is_file())
            self.assertTrue(html.is_file())
            self.assertTrue(data.is_file())
            report_text = markdown.read_text(encoding="utf-8")
            self.assertIn("Executive Summary", report_text)
            self.assertIn("Interpretation Boundary", report_text)
            self.assertIn("Alpha Diversity", report_text)
            self.assertIn("Beta Diversity", report_text)
            self.assertIn("Taxonomic Composition", report_text)
            self.assertIn("iframe", html.read_text(encoding="utf-8"))
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_generate_report_cli_command(self) -> None:
        temp_path = Path("tests") / f"tmp_report_{uuid4().hex}"
        try:
            final_dir = _make_completed_run(temp_path)
            runner = CliRunner()

            result = runner.invoke(cli, ["generate-report", "--final-dir", str(final_dir)])

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("Analysis report generated successfully", result.output)
            self.assertTrue((final_dir / "report" / "analysis_report.md").is_file())
            self.assertTrue((final_dir / "report" / "analysis_report.html").is_file())
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_report_tool_is_registered(self) -> None:
        names = {schema["function"]["name"] for schema in get_tool_schemas()}
        self.assertIn("generate_analysis_report", names)


if __name__ == "__main__":
    unittest.main()
