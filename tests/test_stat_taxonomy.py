"""Tests for differential abundance statistics and plots."""

from __future__ import annotations

import unittest
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pandas as pd
from click.testing import CliRunner

from agent.tools import get_tool_schemas
from process import cli
from src.core.stat_taxonomy import (
    build_differential_comparison_plan,
    run_taxonomy_differential_abundance,
)


def _write_fixture(temp_path: Path) -> tuple[Path, Path, Path]:
    final_dir = temp_path / "work" / "06_final"
    input_dir = temp_path / "work" / "00_input"
    final_dir.mkdir(parents=True, exist_ok=True)
    input_dir.mkdir(parents=True, exist_ok=True)

    sample_ids = [f"KO{i}" for i in range(1, 5)] + [f"WT{i}" for i in range(1, 5)]
    pd.DataFrame(
        {
            "SampleID": sample_ids,
            "Group": ["KO"] * 4 + ["WT"] * 4,
        }
    ).to_csv(input_dir / "metadata.txt", sep="\t", index=False)

    pd.DataFrame(
        {
            "KO1": [100, 1, 10],
            "KO2": [110, 1, 10],
            "KO3": [95, 2, 10],
            "KO4": [105, 1, 10],
            "WT1": [1, 100, 10],
            "WT2": [1, 110, 10],
            "WT3": [2, 95, 10],
            "WT4": [1, 105, 10],
        },
        index=["ASV_1", "ASV_2", "ASV_3"],
    ).to_csv(final_dir / "otutab.txt", sep="\t", index_label="#OTUID")

    pd.DataFrame(
        {
            "OTUID": ["ASV_1", "ASV_2", "ASV_3"],
            "Kingdom": ["Bacteria", "Bacteria", "Bacteria"],
            "Phylum": ["Firmicutes", "Proteobacteria", "Actinobacteria"],
            "Class": ["Bacilli", "Gammaproteobacteria", "Actinobacteria"],
            "Order": ["Lactobacillales", "Enterobacterales", "Streptomycetales"],
            "Family": ["Lactobacillaceae", "Enterobacteriaceae", "Streptomycetaceae"],
            "Genus": ["Lactobacillus", "Escherichia", "Streptomyces"],
            "Species": ["Unassigned", "Unassigned", "Unassigned"],
        }
    ).to_csv(final_dir / "taxonomy.tsv", sep="\t", index=False)
    return final_dir / "otutab.txt", input_dir / "metadata.txt", final_dir / "taxonomy.tsv"


class StatTaxonomyTests(unittest.TestCase):
    """Verify differential abundance planning, execution, CLI, and tools."""

    def test_plan_without_comparison_requires_confirmation(self) -> None:
        temp_path = Path("tests") / f"tmp_stat_{uuid4().hex}"
        try:
            _otutab_path, metadata_path, _taxonomy_path = _write_fixture(temp_path)
            output_dir = temp_path / "statistics"

            result = build_differential_comparison_plan(
                metadata_path=str(metadata_path),
                output_dir=str(output_dir),
            )

            self.assertEqual(result["status"], "plan_required")
            self.assertTrue((output_dir / "comparison_plan.tsv").is_file())
            plan = pd.read_csv(output_dir / "comparison_plan.tsv", sep="\t")
            self.assertEqual(plan.loc[0, "Include"], "no")
            self.assertEqual(plan.loc[0, "Status"], "ready")
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_run_differential_abundance_writes_tables_and_plots(self) -> None:
        temp_path = Path("tests") / f"tmp_stat_{uuid4().hex}"
        try:
            otutab_path, metadata_path, taxonomy_path = _write_fixture(temp_path)
            output_dir = temp_path / "statistics"

            result = run_taxonomy_differential_abundance(
                otutab_path=str(otutab_path),
                metadata_path=str(metadata_path),
                taxonomy_path=str(taxonomy_path),
                output_dir=str(output_dir),
                comparisons=["KO:WT"],
                output_format="html",
            )

            self.assertEqual(result["status"], "completed")
            comparison = result["comparisons"]["KO_vs_WT"]
            self.assertGreaterEqual(comparison["significant_features"], 2)
            result_table = output_dir / "comparison_result" / "KO_vs_WT" / "differential_results.tsv"
            volcano = output_dir / "volcano_chart" / "KO_vs_WT" / "volcano.html"
            heatmap = output_dir / "heatmap_chart" / "KO_vs_WT" / "heatmap.html"
            self.assertTrue(result_table.is_file())
            self.assertTrue(volcano.is_file())
            self.assertTrue(heatmap.is_file())

            table = pd.read_csv(result_table, sep="\t")
            self.assertIn("Phylum", table.columns)
            self.assertIn("Enriched", set(table["level"]))
            self.assertIn("Depleted", set(table["level"]))
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_confirmed_plan_is_not_overwritten_before_execution(self) -> None:
        temp_path = Path("tests") / f"tmp_stat_{uuid4().hex}"
        try:
            otutab_path, metadata_path, taxonomy_path = _write_fixture(temp_path)
            output_dir = temp_path / "statistics"

            plan_result = build_differential_comparison_plan(
                metadata_path=str(metadata_path),
                output_dir=str(output_dir),
            )
            plan_path = Path(plan_result["comparison_plan"])
            plan = pd.read_csv(plan_path, sep="\t")
            plan.loc[0, "Include"] = "yes"
            plan.to_csv(plan_path, sep="\t", index=False)

            result = run_taxonomy_differential_abundance(
                otutab_path=str(otutab_path),
                metadata_path=str(metadata_path),
                taxonomy_path=str(taxonomy_path),
                output_dir=str(output_dir),
                comparison_plan_path=str(plan_path),
                run_confirmed_plan=True,
                output_format="html",
            )

            self.assertEqual(result["status"], "completed")
            self.assertIn("KO_vs_WT", result["comparisons"])
            reread_plan = pd.read_csv(plan_path, sep="\t")
            self.assertEqual(reread_plan.loc[0, "Include"], "yes")
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_cli_differential_abundance_command(self) -> None:
        temp_path = Path("tests") / f"tmp_stat_{uuid4().hex}"
        try:
            otutab_path, metadata_path, taxonomy_path = _write_fixture(temp_path)
            output_dir = temp_path / "statistics"
            runner = CliRunner()

            result = runner.invoke(
                cli,
                [
                    "differential-abundance",
                    "--otutab",
                    str(otutab_path),
                    "--metadata",
                    str(metadata_path),
                    "--taxonomy",
                    str(taxonomy_path),
                    "--output-dir",
                    str(output_dir),
                    "--compare",
                    "KO:WT",
                    "--format",
                    "html",
                ],
            )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("Differential abundance status: completed", result.output)
            self.assertTrue((output_dir / "comparison_result" / "KO_vs_WT" / "differential_results.tsv").is_file())
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_differential_tools_are_registered(self) -> None:
        names = {schema["function"]["name"] for schema in get_tool_schemas()}

        self.assertIn("build_differential_comparison_plan", names)
        self.assertIn("run_taxonomy_differential_abundance", names)
        self.assertIn("plot_differential_volcano", names)
        self.assertIn("plot_differential_heatmap", names)


if __name__ == "__main__":
    unittest.main()
