"""Smoke tests for the process.py CLI pure-Python commands."""

from __future__ import annotations

import importlib
import json
import unittest
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pandas as pd
from click.testing import CliRunner

from agent.evaluation_logger import append_evaluation_event
from process import cli


class ProcessCliTests(unittest.TestCase):
    """CLI smoke tests for alpha, beta, feature-filter, and taxonomy summary."""

    def setUp(self) -> None:
        self.runner = CliRunner()

    def _write_pipeline_params(
        self,
        temp_path: Path,
        *,
        metadata_path: Path,
        seq_dir: Path,
        output_root: Path,
    ) -> Path:
        params_path = temp_path / "pipeline_params.yaml"
        params_path.write_text(
            "\n".join(
                [
                    "run_pipeline:",
                    f"  metadata_path: {metadata_path.as_posix()}",
                    f"  seq_dir: {seq_dir.as_posix()}",
                    f"  output_root: {output_root.as_posix()}",
                    "  read1_suffix: _1.fq.gz",
                    "  read2_suffix: _2.fq.gz",
                    "  fastq_stripleft: 0",
                    "  fastq_stripright: 0",
                    "  fastq_maxee_rate: 0.01",
                    "  feature_method: vsearch-otu",
                    "  feature_minsize: 1",
                    "  feature_identity: 0.97",
                    "  chimera_mode: ref",
                    f"  reference_db: {(Path('databas') / 'rdp_16s_v18.fa').as_posix()}",
                    "  otutab_method: vsearch",
                    "  otutab_identity: 0.97",
                    "  annotation_database: rdp_16s_v18",
                    "  sintax_cutoff: 0.1",
                    "  filter_route: 16s",
                    "  threads: 1",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return params_path

    def _mock_pipeline_dependency_imports(self):
        real_import_module = importlib.import_module

        def fake_import(module_name: str, package: str | None = None):
            if module_name in {"Bio", "pydantic", "numpy", "pandas", "skbio"}:
                return SimpleNamespace(__name__=module_name)
            return real_import_module(module_name, package)

        return fake_import

    def test_alpha_diversity_command_writes_outputs(self) -> None:
        temp_path = Path("tests") / f"tmp_cli_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            input_path = temp_path / "otutab.txt"
            alpha_path = temp_path / "alpha.tsv"
            rarefaction_path = temp_path / "alpha_rarefaction.tsv"

            pd.DataFrame(
                {
                    "S1": [2, 1, 0],
                    "S2": [0, 3, 1],
                },
                index=["OTU1", "OTU2", "OTU3"],
            ).to_csv(input_path, sep="\t")

            result = self.runner.invoke(
                cli,
                [
                    "alpha-diversity",
                    "--input",
                    str(input_path),
                    "--output",
                    str(alpha_path),
                    "--rarefaction-output",
                    str(rarefaction_path),
                    "--depth",
                    "2",
                    "--depth",
                    "4",
                ],
            )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertTrue(alpha_path.is_file())
            self.assertTrue(rarefaction_path.is_file())

            alpha_table = pd.read_csv(alpha_path, sep="\t", index_col=0)
            rarefaction_table = pd.read_csv(rarefaction_path, sep="\t")
            self.assertIn("richness", alpha_table.columns)
            self.assertIn("invsimpson", alpha_table.columns)
            self.assertIn("Depth", rarefaction_table.columns)
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_feature_filter_command_writes_group_abundance_table(self) -> None:
        temp_path = Path("tests") / f"tmp_cli_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            input_path = temp_path / "otutab.txt"
            metadata_path = temp_path / "metadata.txt"
            output_path = temp_path / "group_abundance.tsv"

            pd.DataFrame(
                {
                    "S1": [10, 0, 1],
                    "S2": [10, 0, 1],
                    "S3": [0, 9, 1],
                    "S4": [0, 9, 1],
                },
                index=["OTU1", "OTU2", "OTU3"],
            ).to_csv(input_path, sep="\t")
            pd.DataFrame(
                {
                    "SampleID": ["S1", "S2", "S3", "S4"],
                    "Group": ["A", "A", "B", "B"],
                }
            ).to_csv(metadata_path, sep="\t", index=False)

            result = self.runner.invoke(
                cli,
                [
                    "feature-filter",
                    "--input",
                    str(input_path),
                    "--metadata",
                    str(metadata_path),
                    "--group-col",
                    "Group",
                    "--threshold",
                    "0.25",
                    "--output",
                    str(output_path),
                ],
            )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertTrue(output_path.is_file())

            table = pd.read_csv(output_path, sep="\t", index_col=0)
            self.assertIn("A", table.columns)
            self.assertIn("B", table.columns)
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_beta_diversity_command_writes_distance_matrix(self) -> None:
        temp_path = Path("tests") / f"tmp_cli_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            input_path = temp_path / "otutab.txt"
            output_dir = temp_path / "beta"

            pd.DataFrame(
                {
                    "S1": [1, 0, 2],
                    "S2": [0, 1, 1],
                    "S3": [3, 1, 0],
                },
                index=["OTU1", "OTU2", "OTU3"],
            ).to_csv(input_path, sep="\t")

            result = self.runner.invoke(
                cli,
                [
                    "beta-diversity",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_dir),
                    "--metric",
                    "braycurtis",
                ],
            )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            matrix_path = output_dir / "braycurtis.tsv"
            self.assertTrue(matrix_path.is_file())

            matrix = pd.read_csv(matrix_path, sep="\t", index_col=0)
            self.assertEqual(matrix.shape, (3, 3))
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_agent_evaluation_log_command_summarizes_and_exports(self) -> None:
        temp_path = Path("tests") / f"tmp_cli_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            log_path = temp_path / "agent_evaluation_log.jsonl"
            export_path = temp_path / "agent_evaluation_log_export.json"
            append_evaluation_event(
                {
                    "event_id": "task-1",
                    "event_type": "user_task",
                    "status": "success",
                    "duration_seconds": 0.1,
                },
                log_path=str(log_path),
            )

            result = self.runner.invoke(
                cli,
                [
                    "agent-evaluation-log",
                    "--log-path",
                    str(log_path),
                    "--export-json",
                    str(export_path),
                ],
            )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("Events: 1", result.output)
            self.assertTrue(export_path.is_file())
            payload = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["event_count"], 1)
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_beta_diversity_command_accepts_cityblock_alias_and_writes_manhattan(self) -> None:
        temp_path = Path("tests") / f"tmp_cli_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            input_path = temp_path / "otutab.txt"
            output_dir = temp_path / "beta"

            pd.DataFrame(
                {
                    "S1": [1, 0, 2],
                    "S2": [0, 1, 1],
                    "S3": [3, 1, 0],
                },
                index=["OTU1", "OTU2", "OTU3"],
            ).to_csv(input_path, sep="\t")

            result = self.runner.invoke(
                cli,
                [
                    "beta-diversity",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_dir),
                    "--metric",
                    "cityblock",
                ],
            )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertTrue((output_dir / "manhattan.tsv").is_file())
            self.assertFalse((output_dir / "cityblock.tsv").exists())
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_phylogenetic_tree_command_writes_newick_tree(self) -> None:
        temp_path = Path("tests") / f"tmp_cli_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            fasta_path = temp_path / "otus.fa"
            tree_path = temp_path / "otus.tree"
            fasta_path.write_text(">OTU1\nACGT\n>OTU2\nACGA\n", encoding="utf-8")

            result = self.runner.invoke(
                cli,
                [
                    "phylogenetic-tree",
                    "--input",
                    str(fasta_path),
                    "--output",
                    str(tree_path),
                ],
            )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertTrue(tree_path.is_file())
            self.assertIn("Phylogenetic tree workflow completed successfully", result.output)
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_check_pipeline_config_command_validates_minimal_fixture(self) -> None:
        temp_path = Path("tests") / f"tmp_cli_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            metadata_path = temp_path / "metadata.txt"
            seq_dir = temp_path / "seq"
            output_root = temp_path / "work"
            seq_dir.mkdir(parents=True, exist_ok=True)

            metadata_path.write_text("SampleID\nS1\n", encoding="utf-8")
            (seq_dir / "S1_1.fq.gz").write_bytes(b"")
            (seq_dir / "S1_2.fq.gz").write_bytes(b"")
            params_path = self._write_pipeline_params(
                temp_path,
                metadata_path=metadata_path,
                seq_dir=seq_dir,
                output_root=output_root,
            )

            with patch(
                "process.importlib.import_module",
                side_effect=self._mock_pipeline_dependency_imports(),
            ):
                result = self.runner.invoke(
                    cli,
                    [
                        "check-pipeline-config",
                        "--params",
                        str(params_path),
                    ],
                )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("Pipeline config check: PASSED", result.output)
            self.assertIn("Planned run summary", result.output)
            self.assertIn("Planned provenance JSON", result.output)
            self.assertIn("Planned rarefied OTU table", result.output)
            self.assertIn("Planned alpha rarefaction", result.output)
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_check_pipeline_config_treats_none_tree_path_as_unset(self) -> None:
        temp_path = Path("tests") / f"tmp_cli_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            metadata_path = temp_path / "metadata.txt"
            seq_dir = temp_path / "seq"
            output_root = temp_path / "work"
            seq_dir.mkdir(parents=True, exist_ok=True)

            metadata_path.write_text("SampleID\nS1\n", encoding="utf-8")
            (seq_dir / "S1_1.fq.gz").write_bytes(b"")
            (seq_dir / "S1_2.fq.gz").write_bytes(b"")
            params_path = self._write_pipeline_params(
                temp_path,
                metadata_path=metadata_path,
                seq_dir=seq_dir,
                output_root=output_root,
            )
            params_path.write_text(
                params_path.read_text(encoding="utf-8") + "  beta_tree_path: none\n",
                encoding="utf-8",
            )

            with patch(
                "process.importlib.import_module",
                side_effect=self._mock_pipeline_dependency_imports(),
            ):
                result = self.runner.invoke(
                    cli,
                    [
                        "check-pipeline-config",
                        "--params",
                        str(params_path),
                    ],
                )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("Pipeline config check: PASSED", result.output)
            self.assertNotIn("beta_tree_path", result.output)
            self.assertNotIn("beta_tree_path not found", result.output)
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_check_pipeline_config_treats_dot_tree_path_as_unset(self) -> None:
        temp_path = Path("tests") / f"tmp_cli_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            metadata_path = temp_path / "metadata.txt"
            seq_dir = temp_path / "seq"
            output_root = temp_path / "work"
            seq_dir.mkdir(parents=True, exist_ok=True)

            metadata_path.write_text("SampleID\nS1\n", encoding="utf-8")
            (seq_dir / "S1_1.fq.gz").write_bytes(b"")
            (seq_dir / "S1_2.fq.gz").write_bytes(b"")
            params_path = self._write_pipeline_params(
                temp_path,
                metadata_path=metadata_path,
                seq_dir=seq_dir,
                output_root=output_root,
            )
            params_path.write_text(
                params_path.read_text(encoding="utf-8") + "  beta_tree_path: .\n",
                encoding="utf-8",
            )

            with patch(
                "process.importlib.import_module",
                side_effect=self._mock_pipeline_dependency_imports(),
            ):
                result = self.runner.invoke(
                    cli,
                    [
                        "check-pipeline-config",
                        "--params",
                        str(params_path),
                    ],
                )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("Pipeline config check: PASSED", result.output)
            self.assertNotIn("beta_tree_path", result.output)
            self.assertNotIn("beta_tree_path not found", result.output)
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_run_pipeline_config_check_only_skips_execution(self) -> None:
        temp_path = Path("tests") / f"tmp_cli_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            metadata_path = temp_path / "metadata.txt"
            seq_dir = temp_path / "seq"
            output_root = temp_path / "work"
            seq_dir.mkdir(parents=True, exist_ok=True)

            metadata_path.write_text("SampleID\nS1\n", encoding="utf-8")
            (seq_dir / "S1_1.fq.gz").write_bytes(b"")
            (seq_dir / "S1_2.fq.gz").write_bytes(b"")
            params_path = self._write_pipeline_params(
                temp_path,
                metadata_path=metadata_path,
                seq_dir=seq_dir,
                output_root=output_root,
            )

            with patch(
                "process.importlib.import_module",
                side_effect=self._mock_pipeline_dependency_imports(),
            ):
                result = self.runner.invoke(
                    cli,
                    [
                        "run-pipeline-config",
                        "--params",
                        str(params_path),
                        "--check-only",
                    ],
                )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("Check-only mode completed without blocking issues.", result.output)
            self.assertFalse((output_root / "06_final" / "run_summary.json").exists())
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_write_provenance_command_updates_existing_summary(self) -> None:
        temp_path = Path("tests") / f"tmp_cli_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            final_dir = temp_path / "work" / "06_final"
            final_dir.mkdir(parents=True, exist_ok=True)
            output_table = final_dir / "otutab.txt"
            output_table.write_text("#OTUID\tS1\nOTU1\t1\n", encoding="utf-8")
            summary_path = final_dir / "run_summary.json"
            summary_path.write_text(
                (
                    "{\n"
                    '  "status": "success",\n'
                    '  "started_at": "2026-01-01T00:00:00+00:00",\n'
                    '  "completed_at": "2026-01-01T00:00:01+00:00",\n'
                    '  "effective_params": {"output_root": "work"},\n'
                    f'  "outputs": {{"final_outputs": {{"feature_table": "{output_table.as_posix()}"}}}},\n'
                    '  "steps": []\n'
                    "}\n"
                ),
                encoding="utf-8",
            )

            result = self.runner.invoke(
                cli,
                [
                    "write-provenance",
                    "--summary",
                    str(summary_path),
                ],
            )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertTrue((final_dir / "provenance.json").is_file())
            self.assertTrue((final_dir / "provenance.md").is_file())
            updated_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertIn("provenance", updated_summary)
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_database_registry_commands(self) -> None:
        temp_path = Path("tests") / f"tmp_cli_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            fasta_path = temp_path / "custom.fa"
            fasta_path.write_text(">OTU1\nACGT\n", encoding="utf-8")
            registry_path = temp_path / "databases.yaml"

            register_result = self.runner.invoke(
                cli,
                [
                    "register-database",
                    "--name",
                    "custom_16s",
                    "--path",
                    str(fasta_path),
                    "--version",
                    "v1",
                    "--registry",
                    str(registry_path),
                    "--alias",
                    "custom",
                ],
            )
            self.assertEqual(register_result.exit_code, 0, msg=register_result.output)
            self.assertTrue(registry_path.is_file())

            list_result = self.runner.invoke(
                cli,
                [
                    "list-databases",
                    "--registry",
                    str(registry_path),
                    "--no-builtins",
                ],
            )
            self.assertEqual(list_result.exit_code, 0, msg=list_result.output)
            self.assertIn("custom_16s", list_result.output)

            check_result = self.runner.invoke(
                cli,
                [
                    "check-database",
                    "custom",
                    "--registry",
                    str(registry_path),
                    "--no-hash",
                ],
            )
            self.assertEqual(check_result.exit_code, 0, msg=check_result.output)
            self.assertIn("Status: passed", check_result.output)
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_cli_only_workflow_command_documents_no_llm_path(self) -> None:
        result = self.runner.invoke(
            cli,
            [
                "cli-only-workflow",
                "--params",
                "pipeline_params.yaml",
                "--output-root",
                "work",
            ],
        )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("does not require an LLM API key", result.output)
        self.assertIn("check-pipeline-config --params pipeline_params.yaml", result.output)
        self.assertIn("run-pipeline-config --params pipeline_params.yaml", result.output)
        self.assertIn("visualization-suite --final-dir", result.output)
        self.assertIn("generate-report --final-dir", result.output)

    def test_taxonomy_summary_command_writes_taxonomy_and_rank_tables(self) -> None:
        temp_path = Path("tests") / f"tmp_cli_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            sintax_path = temp_path / "otus.sintax"
            input_path = temp_path / "otutab.txt"
            output_dir = temp_path / "taxonomy"

            sintax_path.write_text(
                "\n".join(
                    [
                        (
                            "OTU1\t"
                            "d:Bacteria(1.0),p:Firmicutes(0.9),g:Lactobacillus(0.8)\t+\t"
                            "d:Bacteria,p:Firmicutes,g:Lactobacillus"
                        ),
                        (
                            "OTU2\t"
                            "d:Bacteria(1.0),p:Proteobacteria(0.9),g:Escherichia(0.8)\t+\t"
                            "d:Bacteria,p:Proteobacteria,g:Escherichia"
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            pd.DataFrame(
                {
                    "S1": [10, 3],
                    "S2": [5, 4],
                },
                index=["OTU1", "OTU2"],
            ).to_csv(input_path, sep="\t")

            result = self.runner.invoke(
                cli,
                [
                    "taxonomy-summary",
                    "--sintax",
                    str(sintax_path),
                    "--otutab",
                    str(input_path),
                    "--rank",
                    "Phylum",
                    "--rank",
                    "Genus",
                    "--output",
                    str(output_dir),
                ],
            )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertTrue((output_dir / "taxonomy.tsv").is_file())
            self.assertTrue((output_dir / "taxonomy_summary" / "phylum.tsv").is_file())
            self.assertTrue((output_dir / "taxonomy_summary" / "genus.tsv").is_file())
        finally:
            rmtree(temp_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
