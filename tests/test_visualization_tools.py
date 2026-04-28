"""Tests for visualization tool entry points."""

from __future__ import annotations

import unittest
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import numpy as np
import pandas as pd
from click.testing import CliRunner

from agent.tools import get_tool_schemas
from process import cli
from src.core.viz_common import validate_output_format
from src.core.viz_beta_diversity import plot_beta_cpcoa, plot_beta_pcoa
from src.core.viz_pipeline import run_visualization_suite


def _make_minimal_completed_run(temp_path: Path) -> Path:
    final_dir = temp_path / "work" / "06_final"
    alpha_dir = final_dir / "alpha"
    beta_dir = final_dir / "beta"
    taxonomy_dir = final_dir / "taxonomy_summary"
    input_dir = temp_path / "work" / "00_input"
    for directory in (alpha_dir, beta_dir, taxonomy_dir, input_dir):
        directory.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        {
            "SampleID": ["S1", "S2", "S3"],
            "Group": ["A", "A", "B"],
        }
    ).to_csv(input_dir / "metadata.txt", sep="\t", index=False)
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
        {
            "richness": [1, 2, 3],
            "S1": [3, 6, 10],
            "S2": [4, 8, 12],
            "S3": [2, 5, 8],
        }
    ).to_csv(alpha_dir / "alpha_rarefaction.tsv", sep="\t", index=False)
    pd.DataFrame(
        [
            [0.0, 0.2, 0.4],
            [0.2, 0.0, 0.3],
            [0.4, 0.3, 0.0],
        ],
        index=["S1", "S2", "S3"],
        columns=["S1", "S2", "S3"],
    ).to_csv(beta_dir / "braycurtis.tsv", sep="\t", index_label="SampleID")
    pd.DataFrame(
        {
            "Phylum": ["Firmicutes", "Proteobacteria"],
            "S1": [60.0, 40.0],
            "S2": [55.0, 45.0],
            "S3": [25.0, 75.0],
            "All": [50.0, 50.0],
        }
    ).to_csv(taxonomy_dir / "phylum.tsv", sep="\t", index=False)
    return final_dir


class VisualizationToolTests(unittest.TestCase):
    """Verify visualization tools can run on a minimal completed run."""

    def test_visualization_suite_generates_expected_outputs(self) -> None:
        temp_path = Path("tests") / f"tmp_viz_{uuid4().hex}"
        try:
            final_dir = _make_minimal_completed_run(temp_path)

            result = run_visualization_suite(
                final_dir=str(final_dir),
                output_format="html",
                include_cpcoa=False,
                include_beta_stats=False,
                color_palette="A:#111111,B:#222222",
            )

            generated_files = [Path(path) for path in result["generated_files"]]
            self.assertTrue(generated_files)
            self.assertTrue((final_dir / "plots" / "alpha_boxplot_chart" / "alpha_boxplots.html").is_file())
            self.assertTrue((final_dir / "plots" / "index.html").is_file())
            self.assertTrue((final_dir / "plots" / "alpha_boxplot_chart" / "index.html").is_file())
            self.assertTrue((final_dir / "plots" / "beta_pcoa_chart" / "beta_pcoa_report.html").is_file())
            self.assertTrue(
                (
                    final_dir
                    / "plots"
                    / "taxonomy_stacked_bar_chart"
                    / "taxonomy_stacked_bar_report.html"
                ).is_file()
            )
            self.assertTrue(
                (
                    final_dir
                    / "plots"
                    / "taxonomy_heatmap_chart"
                    / "taxonomy_heatmap_report.html"
                ).is_file()
            )
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_visualization_tools_are_registered(self) -> None:
        names = {schema["function"]["name"] for schema in get_tool_schemas()}

        self.assertIn("run_visualization_suite", names)
        self.assertIn("plot_alpha_boxplots", names)
        self.assertIn("plot_beta_pcoa", names)
        self.assertIn("plot_taxonomy_heatmaps", names)
        schemas = {schema["function"]["name"]: schema for schema in get_tool_schemas()}
        output_enum = schemas["run_visualization_suite"]["function"]["parameters"]["properties"]["output_format"]["enum"]
        self.assertIn("svg", output_enum)
        self.assertIn("color_palette", schemas["run_visualization_suite"]["function"]["parameters"]["properties"])

    def test_individual_visualization_defaults_use_chart_subdirectories(self) -> None:
        schemas = {schema["function"]["name"]: schema for schema in get_tool_schemas()}

        alpha_default = schemas["plot_alpha_boxplots"]["function"]["parameters"]["properties"]["output_dir"]["default"]
        beta_default = schemas["plot_beta_pcoa"]["function"]["parameters"]["properties"]["output_dir"]["default"]
        taxonomy_default = schemas["plot_taxonomy_heatmaps"]["function"]["parameters"]["properties"]["output_dir"]["default"]

        self.assertTrue(alpha_default.endswith("alpha_boxplot_chart"))
        self.assertTrue(beta_default.endswith("beta_pcoa_chart"))
        self.assertTrue(taxonomy_default.endswith("taxonomy_heatmap_chart"))

    def test_visualization_suite_rejects_invalid_output_format(self) -> None:
        temp_path = Path("tests") / f"tmp_viz_{uuid4().hex}"
        try:
            final_dir = _make_minimal_completed_run(temp_path)

            with self.assertRaises(ValueError):
                run_visualization_suite(final_dir=str(final_dir), output_format="bad")
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_visualization_output_format_accepts_svg(self) -> None:
        self.assertEqual(validate_output_format("svg"), "svg")

    def test_pcoa_uses_reference_orientation_and_colors(self) -> None:
        temp_path = Path("tests") / f"tmp_pcoa_{uuid4().hex}"
        try:
            beta_dir = temp_path / "beta"
            beta_dir.mkdir(parents=True, exist_ok=True)
            metadata_path = temp_path / "metadata.txt"
            output_dir = temp_path / "pcoa"

            sample_ids = ["WT1", "KO1", "OE1", "WT2"]
            coordinates = np.array(
                [
                    [0.0, 0.00],
                    [1.0, 0.03],
                    [2.0, -0.02],
                    [3.0, 0.01],
                ],
                dtype=float,
            )
            distances = np.sqrt(((coordinates[:, None, :] - coordinates[None, :, :]) ** 2).sum(axis=2))
            pd.DataFrame(distances, index=sample_ids, columns=sample_ids).to_csv(
                beta_dir / "braycurtis.tsv",
                sep="\t",
                index_label="SampleID",
            )
            pd.DataFrame({"SampleID": sample_ids, "Group": ["WT", "KO", "OE", "WT"]}).to_csv(
                metadata_path,
                sep="\t",
                index=False,
            )

            result = plot_beta_pcoa(
                beta_dir=str(beta_dir),
                metadata_path=str(metadata_path),
                output_dir=str(output_dir),
                metrics=["braycurtis"],
                output_format="html",
            )

            coord_table = pd.read_csv(result["coordinates"], sep="\t")
            axis1 = coord_table["Axis1"].to_numpy(dtype=float)
            self.assertLess(axis1[np.argmax(np.abs(axis1))], 0)
            html = (output_dir / "beta_pcoa_braycurtis.html").read_text(encoding="utf-8")
            self.assertIn("#F8766D", html)
            self.assertIn("#00BA38", html)
            self.assertIn("#619CFF", html)
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_cpcoa_keeps_sample_level_coordinates_within_groups(self) -> None:
        temp_path = Path("tests") / f"tmp_cpcoa_{uuid4().hex}"
        try:
            beta_dir = temp_path / "beta"
            beta_dir.mkdir(parents=True, exist_ok=True)
            metadata_path = temp_path / "metadata.txt"
            output_dir = temp_path / "cpcoa"

            sample_ids = [
                "WT1",
                "WT2",
                "WT3",
                "KO1",
                "KO2",
                "KO3",
                "OE1",
                "OE2",
                "OE3",
            ]
            groups = ["WT", "WT", "WT", "KO", "KO", "KO", "OE", "OE", "OE"]
            coordinates = np.array(
                [
                    [0.08, 0.36],
                    [0.16, 0.30],
                    [0.02, 0.26],
                    [-0.42, -0.03],
                    [-0.34, -0.12],
                    [-0.22, -0.08],
                    [0.22, -0.12],
                    [0.29, -0.24],
                    [0.18, -0.30],
                ],
                dtype=float,
            )
            distances = np.sqrt(((coordinates[:, None, :] - coordinates[None, :, :]) ** 2).sum(axis=2))
            pd.DataFrame(distances, index=sample_ids, columns=sample_ids).to_csv(
                beta_dir / "braycurtis.tsv",
                sep="\t",
                index_label="SampleID",
            )
            pd.DataFrame({"SampleID": sample_ids, "Group": groups}).to_csv(
                metadata_path,
                sep="\t",
                index=False,
            )

            result = plot_beta_cpcoa(
                beta_dir=str(beta_dir),
                metadata_path=str(metadata_path),
                output_dir=str(output_dir),
                metrics=["braycurtis"],
                permutations=9,
                random_seed=1,
                output_format="html",
            )

            coord_table = pd.read_csv(result["coordinates"], sep="\t")
            wt_values = coord_table.loc[coord_table["Group"] == "WT", "Axis1"].round(10)
            self.assertGreater(wt_values.nunique(), 1)
            html = (output_dir / "beta_cpcoa_braycurtis.html").read_text(encoding="utf-8")
            self.assertIn("Beta Diversity CPCoA - Bray-Curtis", html)
            self.assertIn("CAP1", html)
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_process_visualization_suite_command(self) -> None:
        temp_path = Path("tests") / f"tmp_viz_{uuid4().hex}"
        try:
            final_dir = _make_minimal_completed_run(temp_path)
            output_dir = temp_path / "charts"
            runner = CliRunner()

            result = runner.invoke(
                cli,
                [
                    "visualization-suite",
                    "--final-dir",
                    str(final_dir),
                    "--output-dir",
                    str(output_dir),
                    "--format",
                    "html",
                    "--color-palette",
                    "A:#111111,B:#222222",
                    "--skip-cpcoa",
                    "--skip-beta-stats",
                ],
            )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("Visualization suite completed successfully", result.output)
            self.assertTrue((output_dir / "index.html").is_file())
            self.assertTrue((output_dir / "alpha_boxplot_chart" / "alpha_boxplots.html").is_file())
            self.assertTrue((output_dir / "taxonomy_heatmap_chart" / "taxonomy_heatmap_report.html").is_file())
        finally:
            rmtree(temp_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
