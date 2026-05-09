"""Tests for post-filter analysis outputs in the raw amplicon pipeline."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pandas as pd

from src.core.raw_amplicon_pipeline import (
    MERGE_BACKEND_PYTHON,
    MERGE_BACKEND_VSEARCH,
    PipelineContext,
    _generate_analysis_outputs,
    _prefix_fastq_headers,
    _step_merge_pairs,
    run_raw_amplicon_pipeline,
)


class RawAmpliconPipelineAnalysisTests(unittest.TestCase):
    """Verify that final analysis outputs are written after filtering."""

    def _write_pipeline_fixture(self, temp_path: Path) -> tuple[Path, Path, Path]:
        metadata_path = temp_path / "metadata.txt"
        seq_dir = temp_path / "seq"
        output_root = temp_path / "work"
        seq_dir.mkdir(parents=True, exist_ok=True)

        metadata_path.write_text("SampleID\nS1\n", encoding="utf-8")
        (seq_dir / "S1_1.fq.gz").write_bytes(b"")
        (seq_dir / "S1_2.fq.gz").write_bytes(b"")
        return metadata_path, seq_dir, output_root

    def _mock_mergepairs(self):
        def fake_mergepairs(read1_path: str, read2_path: str, output_path: str) -> dict[str, object]:
            Path(output_path).write_text(
                "@SEQ1\nACGT\n+\nIIII\n",
                encoding="utf-8",
            )
            return {
                "read1_path": read1_path,
                "read2_path": read2_path,
                "merged_records": 1,
            }

        return fake_mergepairs

    def _mock_fastx_filter(self):
        def fake_run(config: dict[str, object]) -> SimpleNamespace:
            Path(str(config["fastaout"])).write_text(">OTU1\nACGT\n", encoding="utf-8")
            return SimpleNamespace(success=True, error=None)

        return fake_run

    def _mock_derep(self):
        def fake_run(config: dict[str, object]) -> SimpleNamespace:
            Path(str(config["output"])).write_text(">Uni_1;size=1\nACGT\n", encoding="utf-8")
            return SimpleNamespace(success=True, error=None)

        return fake_run

    def _mock_feature_generation(self):
        def fake_run(
            feature_method: str,
            uniques_fasta: str,
            features_dir: str,
            feature_minsize: int,
            threads: int,
            usearch_path: str | None,
            vsearch_path: str | None,
            feature_identity: float,
            command_timeout: float | None,
        ) -> dict[str, object]:
            final_feature_fasta = Path(features_dir) / "otus.fa"
            final_feature_fasta.parent.mkdir(parents=True, exist_ok=True)
            final_feature_fasta.write_text(">OTU1\nACGT\n", encoding="utf-8")
            return {
                "feature_method": feature_method,
                "otu_fasta": str(final_feature_fasta),
                "feature_minsize": feature_minsize,
                "threads": threads,
                "usearch_path": usearch_path,
                "vsearch_path": vsearch_path,
                "feature_identity": feature_identity,
                "command_timeout": command_timeout,
                "uniques_fasta": uniques_fasta,
            }

        return fake_run

    def _mock_chimera_filter(self):
        def fake_run(
            *,
            output_fasta_path: str,
            output_dir: str,
            reference_db: str,
            **_: object,
        ) -> dict[str, object]:
            Path(output_fasta_path).write_text(">OTU1\nACGT\n", encoding="utf-8")
            uchime_dir = Path(output_dir)
            uchime_dir.mkdir(parents=True, exist_ok=True)
            (uchime_dir / "01_uchime_report.tsv").write_text("OTU1\tN\n", encoding="utf-8")
            return {
                "reference_db": reference_db,
                "result_fasta": output_fasta_path,
                "uchime_report": str(uchime_dir / "01_uchime_report.tsv"),
            }

        return fake_run

    def _mock_otutab_generation(self):
        def fake_run(
            *,
            output_table_path: str,
            representative_fasta: str,
            input_fasta: str,
            method: str,
            **_: object,
        ) -> dict[str, object]:
            pd.DataFrame({"S1": [5]}, index=["OTU1"]).to_csv(output_table_path, sep="\t")
            return {
                "method": method,
                "otutab": output_table_path,
                "representative_fasta": representative_fasta,
                "input_fasta": input_fasta,
            }

        return fake_run

    def _mock_sintax(self):
        def fake_run(
            *,
            output_annotation_path: str,
            database: str,
            sintax_cutoff: float,
            **_: object,
        ) -> dict[str, object]:
            Path(output_annotation_path).write_text(
                (
                    "OTU1\t"
                    "d:Bacteria(1.0),p:Firmicutes(0.9),g:Lactobacillus(0.8)\t+\t"
                    "d:Bacteria,p:Firmicutes,g:Lactobacillus\n"
                ),
                encoding="utf-8",
            )
            return {
                "database": database,
                "sintax_cutoff": sintax_cutoff,
                "output": output_annotation_path,
            }

        return fake_run

    def _mock_otutab_filter(self):
        def fake_run(
            *,
            input_table: str,
            taxonomy_path: str,
            representative_fasta: str,
            output_table_path: str,
            output_fasta_path: str,
            output_taxonomy_path: str,
            output_id_path: str,
            output_stat_path: str | None,
            **_: object,
        ) -> dict[str, object]:
            table = pd.read_csv(input_table, sep="\t", index_col=0)
            table.to_csv(output_table_path, sep="\t")
            Path(output_fasta_path).write_text(Path(representative_fasta).read_text(encoding="utf-8"), encoding="utf-8")
            Path(output_taxonomy_path).write_text(Path(taxonomy_path).read_text(encoding="utf-8"), encoding="utf-8")
            Path(output_id_path).write_text("OTU1\n", encoding="utf-8")
            if output_stat_path is not None:
                Path(output_stat_path).write_text("kept\t1\n", encoding="utf-8")
            return {
                "feature_table": output_table_path,
                "representative_fasta": output_fasta_path,
                "taxonomy": output_taxonomy_path,
                "feature_ids": output_id_path,
                "stat_path": output_stat_path,
            }

        return fake_run

    def test_generate_analysis_outputs_writes_expected_files(self) -> None:
        temp_path = Path("tests") / f"tmp_pipeline_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            otutab_path = temp_path / "otutab.txt"
            sintax_path = temp_path / "otus.sintax"
            output_dir = temp_path / "final"

            pd.DataFrame(
                {
                    "S1": [10, 3],
                    "S2": [5, 4],
                },
                index=["OTU1", "OTU2"],
            ).to_csv(otutab_path, sep="\t")
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

            outputs = _generate_analysis_outputs(
                otutab_path=str(otutab_path),
                sintax_path=str(sintax_path),
                output_dir=str(output_dir),
            )

            self.assertTrue(Path(outputs["taxonomy_table"]).is_file())
            self.assertTrue(Path(outputs["rarefied_otutab"]).is_file())
            self.assertTrue(Path(outputs["alpha_diversity"]).is_file())
            self.assertTrue(Path(outputs["alpha_rarefaction"]).is_file())
            self.assertTrue((output_dir / "beta" / "braycurtis.tsv").is_file())
            self.assertTrue((output_dir / "taxonomy_summary" / "genus.tsv").is_file())
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_prefix_fastq_headers_preserves_records_and_prefixes_sample_id(self) -> None:
        temp_path = Path("tests") / f"tmp_pipeline_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            fastq_path = temp_path / "merged.fq"
            fastq_path.write_text(
                "\n".join(
                    [
                        "@HISEQ:1:1",
                        "ACGT",
                        "+",
                        "IIII",
                        "@HISEQ:1:2",
                        "TGCA",
                        "+",
                        "JJJJ",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            _prefix_fastq_headers(str(fastq_path), "KO1")

            self.assertEqual(
                fastq_path.read_text(encoding="utf-8").splitlines(),
                [
                    "@KO1.HISEQ:1:1",
                    "ACGT",
                    "+",
                    "IIII",
                    "@KO1.HISEQ:1:2",
                    "TGCA",
                    "+",
                    "JJJJ",
                ],
            )
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_step_merge_pairs_uses_vsearch_backend(self) -> None:
        temp_path = Path("tests") / f"tmp_pipeline_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            merged_dir = temp_path / "01_merged"
            merged_dir.mkdir()
            read1_path = temp_path / "S1_1.fq.gz"
            read2_path = temp_path / "S1_2.fq.gz"
            read1_path.write_bytes(b"")
            read2_path.write_bytes(b"")
            calls: list[tuple[list[str], float | None]] = []

            def fake_run_command(command: list[str], timeout: float | None = None):
                calls.append((command, timeout))
                output_path = Path(command[command.index("--fastqout") + 1])
                output_path.write_text("@SEQ1\nACGT\n+\nIIII\n", encoding="utf-8")
                return SimpleNamespace(command=command, returncode=0)

            context = PipelineContext(
                work_dirs={"merged": str(merged_dir)},
                summary_path=str(temp_path / "run_summary.json"),
                provenance_path=str(temp_path / "provenance.json"),
                provenance_md_path=str(temp_path / "provenance.md"),
                summary={
                    "effective_params": {
                        "vsearch_path": "mock-vsearch.exe",
                        "threads": 4,
                        "command_timeout": 12,
                    }
                },
                resolved={"merge_backend": MERGE_BACKEND_VSEARCH},
                results={"read_pairs": [("S1", str(read1_path), str(read2_path))]},
            )

            with (
                patch("src.core.raw_amplicon_pipeline.resolve_executable", return_value="mock-vsearch.exe"),
                patch("src.core.raw_amplicon_pipeline.run_command", side_effect=fake_run_command),
            ):
                result = _step_merge_pairs(context)

            command, timeout = calls[0]
            self.assertEqual(timeout, 12)
            self.assertIn("--fastq_mergepairs", command)
            self.assertIn(str(read1_path), command)
            self.assertIn("--reverse", command)
            self.assertIn(str(read2_path), command)
            self.assertIn("--threads", command)
            self.assertIn("4", command)
            self.assertIn("--fastq_minovlen", command)
            self.assertIn("--fastq_maxdiffs", command)
            self.assertEqual(result["backend"], MERGE_BACKEND_VSEARCH)
            self.assertEqual(
                (merged_dir / "all.fq").read_text(encoding="utf-8"),
                "@S1.SEQ1\nACGT\n+\nIIII\n",
            )
            self.assertEqual(
                context.results["merge_summaries"][0]["backend"],
                MERGE_BACKEND_VSEARCH,
            )
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_step_merge_pairs_keeps_python_fallback(self) -> None:
        temp_path = Path("tests") / f"tmp_pipeline_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            merged_dir = temp_path / "01_merged"
            merged_dir.mkdir()
            read1_path = temp_path / "S1_1.fq.gz"
            read2_path = temp_path / "S1_2.fq.gz"
            read1_path.write_bytes(b"")
            read2_path.write_bytes(b"")
            context = PipelineContext(
                work_dirs={"merged": str(merged_dir)},
                summary_path=str(temp_path / "run_summary.json"),
                provenance_path=str(temp_path / "provenance.json"),
                provenance_md_path=str(temp_path / "provenance.md"),
                summary={"effective_params": {"threads": 1}},
                resolved={"merge_backend": MERGE_BACKEND_PYTHON},
                results={"read_pairs": [("S1", str(read1_path), str(read2_path))]},
            )

            with (
                patch(
                    "src.core.raw_amplicon_pipeline._load_vendor_fastq_mergepairs",
                    return_value=self._mock_mergepairs(),
                ) as load_mergepairs,
                patch("src.core.raw_amplicon_pipeline.resolve_executable") as resolve_executable,
            ):
                result = _step_merge_pairs(context)

            load_mergepairs.assert_called_once()
            resolve_executable.assert_not_called()
            self.assertEqual(result["backend"], MERGE_BACKEND_PYTHON)
            self.assertEqual(
                context.results["merge_summaries"][0]["backend"],
                MERGE_BACKEND_PYTHON,
            )
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_run_raw_amplicon_pipeline_writes_success_summary(self) -> None:
        temp_path = Path("tests") / f"tmp_pipeline_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            metadata_path, seq_dir, output_root = self._write_pipeline_fixture(temp_path)

            with (
                patch(
                    "src.core.raw_amplicon_pipeline._load_vendor_fastq_mergepairs",
                    return_value=self._mock_mergepairs(),
                ),
                patch(
                    "src.core.raw_amplicon_pipeline._load_vendor_fastx_filter_run",
                    return_value=self._mock_fastx_filter(),
                ),
                patch(
                    "src.core.raw_amplicon_pipeline._load_vendor_derep_run",
                    return_value=self._mock_derep(),
                ),
                patch(
                    "src.core.raw_amplicon_pipeline._run_feature_generation",
                    side_effect=self._mock_feature_generation(),
                ),
                patch(
                    "src.core.raw_amplicon_pipeline.run_vsearch_uchime_ref",
                    side_effect=self._mock_chimera_filter(),
                ),
                patch(
                    "src.core.raw_amplicon_pipeline.run_otutab_generation",
                    side_effect=self._mock_otutab_generation(),
                ),
                patch(
                    "src.core.raw_amplicon_pipeline.run_vsearch_sintax",
                    side_effect=self._mock_sintax(),
                ),
                patch(
                    "src.core.raw_amplicon_pipeline.run_otutab_filter",
                    side_effect=self._mock_otutab_filter(),
                ),
            ):
                outputs = run_raw_amplicon_pipeline(
                    metadata_path=str(metadata_path),
                    seq_dir=str(seq_dir),
                    output_root=str(output_root),
                    fastq_stripleft=0,
                    fastq_stripright=0,
                    fastq_maxee_rate=0.01,
                    feature_minsize=1,
                    feature_method="vsearch-otu",
                    feature_identity=0.97,
                    chimera_mode="ref",
                    reference_db=str(Path("databas") / "rdp_16s_v18.fa"),
                    otutab_method="vsearch",
                    otutab_identity=0.97,
                    annotation_database="rdp_16s_v18",
                    sintax_cutoff=0.1,
                    filter_route="16s",
                    threads=1,
                    merge_backend=MERGE_BACKEND_PYTHON,
                    usearch_path="",
                    vsearch_path="",
                    beta_tree_path=".",
                    params_source=str(temp_path / "pipeline_params.yaml"),
                )

            summary_path = Path(outputs["summary_path"])
            self.assertTrue(summary_path.is_file())

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "success")
            self.assertIsNone(summary["failed_step"])
            self.assertEqual(summary["effective_params"]["params_source"], str((temp_path / "pipeline_params.yaml").resolve()))
            self.assertEqual(summary["effective_params"]["merge_backend"], MERGE_BACKEND_PYTHON)
            self.assertIsNone(summary["effective_params"]["usearch_path"])
            self.assertIsNone(summary["effective_params"]["vsearch_path"])
            self.assertTrue(Path(summary["effective_params"]["beta_tree_path"]).is_file())
            self.assertEqual(summary["outputs"]["final_outputs"]["feature_table"], outputs["final_outputs"]["feature_table"])
            self.assertTrue(Path(outputs["phylogenetic_tree"]["tree_path"]).is_file())
            self.assertEqual(outputs["phylogenetic_tree"]["source"], "generated")
            self.assertEqual(
                summary["outputs"]["analysis_outputs"]["rarefied_otutab"],
                outputs["analysis_outputs"]["rarefied_otutab"],
            )
            self.assertIn("provenance", outputs)
            provenance_json = Path(outputs["provenance"]["json"])
            provenance_md = Path(outputs["provenance"]["markdown"])
            self.assertTrue(provenance_json.is_file())
            self.assertTrue(provenance_md.is_file())

            provenance = json.loads(provenance_json.read_text(encoding="utf-8"))
            self.assertEqual(provenance["schema_version"], "1.0")
            self.assertEqual(provenance["workflow"]["status"], "success")
            self.assertIn("commit", provenance["project"])
            self.assertIn("python_version", provenance["runtime"])
            self.assertIn("packages", provenance["runtime"])
            self.assertIn("effective_params", provenance)
            self.assertTrue(provenance["final_file_hashes"])
            self.assertTrue(
                all("sha256" in item for item in provenance["final_file_hashes"])
            )

            steps_by_name = {step["name"]: step for step in summary["steps"]}
            self.assertEqual(steps_by_name["generate_phylogenetic_tree"]["status"], "completed")
            self.assertIn("duration_seconds", steps_by_name["generate_phylogenetic_tree"])
            self.assertEqual(steps_by_name["generate_analysis_outputs"]["status"], "completed")
            self.assertEqual(
                steps_by_name["generate_analysis_outputs"]["details"]["rarefaction_depth"],
                outputs["analysis_outputs"]["rarefaction_depth"],
            )
            self.assertEqual(
                steps_by_name["generate_analysis_outputs"]["details"]["skipped_beta_metrics"],
                [],
            )
            self.assertIn(
                "weighted_unifrac",
                steps_by_name["generate_analysis_outputs"]["details"]["generated_beta_metrics"],
            )
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_run_raw_amplicon_pipeline_writes_failure_summary(self) -> None:
        temp_path = Path("tests") / f"tmp_pipeline_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            metadata_path, seq_dir, output_root = self._write_pipeline_fixture(temp_path)
            orphan_temp = output_root / "01_merged" / "orphan.tmp"

            mergepairs = self._mock_mergepairs()

            def mergepairs_with_temp(
                read1_path: str,
                read2_path: str,
                output_path: str,
            ) -> dict[str, object]:
                result = mergepairs(read1_path, read2_path, output_path)
                orphan_temp.parent.mkdir(parents=True, exist_ok=True)
                orphan_temp.write_text("stale temp file\n", encoding="utf-8")
                return result

            def failing_fastx_filter(config: dict[str, object]) -> SimpleNamespace:
                return SimpleNamespace(
                    success=False,
                    error=SimpleNamespace(message="mock filter failure"),
                )

            with (
                patch(
                    "src.core.raw_amplicon_pipeline._load_vendor_fastq_mergepairs",
                    return_value=mergepairs_with_temp,
                ),
                patch(
                    "src.core.raw_amplicon_pipeline._load_vendor_fastx_filter_run",
                    return_value=failing_fastx_filter,
                ),
            ):
                with self.assertRaisesRegex(ValueError, "mock filter failure"):
                    run_raw_amplicon_pipeline(
                        metadata_path=str(metadata_path),
                        seq_dir=str(seq_dir),
                        output_root=str(output_root),
                        fastq_stripleft=0,
                        fastq_stripright=0,
                        fastq_maxee_rate=0.01,
                        merge_backend=MERGE_BACKEND_PYTHON,
                    )

            summary_path = output_root / "06_final" / "run_summary.json"
            self.assertTrue(summary_path.is_file())

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["failed_step"], "filter_reads")
            self.assertEqual(summary["error"], "mock filter failure")
            self.assertFalse(orphan_temp.exists())
            self.assertIn(str(orphan_temp.resolve()), summary["cleanup"]["cleaned_paths"])
            self.assertTrue((output_root / "06_final" / "provenance.json").is_file())
            provenance = json.loads(
                (output_root / "06_final" / "provenance.json").read_text(encoding="utf-8")
            )
            self.assertEqual(provenance["workflow"]["status"], "failed")
            failed_steps = {
                step["name"]: step for step in provenance["steps"]
            }
            self.assertEqual(failed_steps["filter_reads"]["status"], "failed")
        finally:
            rmtree(temp_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
