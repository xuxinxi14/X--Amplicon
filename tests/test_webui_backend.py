"""Unit tests for Web UI backend services."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from shutil import rmtree
from unittest.mock import patch
from uuid import uuid4

import yaml

from webui.backend.models.common import CommandSpec
from webui.backend.models.project import PipelineParamsDraft, ProjectRecord
from webui.backend.models.settings import WebUISettings
from webui.backend.services import command_builder
from webui.backend.services.fastq_pairing import preview_fastq_pairs
from webui.backend.services.file_service import read_text_file, resolve_authorized_path
from webui.backend.services.job_manager import JobManager
from webui.backend.services.metadata_validator import validate_metadata
from webui.backend.services.params_writer import write_pipeline_params
from webui.backend.services.result_indexer import build_result_index


class WebUIBackendServiceTests(unittest.TestCase):
    """Cover Web UI pure-logic services without running the full pipeline."""

    def setUp(self) -> None:
        self.temp_path = Path("tests") / f"tmp_webui_backend_{uuid4().hex}"
        self.temp_path.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        rmtree(self.temp_path, ignore_errors=True)

    def _write_metadata(self, content: str = "SampleID\tGroup\nS1\tWT\nS2\tKO\n") -> Path:
        metadata_path = self.temp_path / "metadata.tsv"
        metadata_path.write_text(content, encoding="utf-8")
        return metadata_path

    def test_metadata_validation_reports_valid_groups_and_missing_columns(self) -> None:
        metadata_path = self._write_metadata()

        result = validate_metadata(str(metadata_path))

        self.assertEqual(result.status, "passed")
        self.assertEqual(result.sample_count, 2)
        self.assertEqual([group.group for group in result.groups], ["KO", "WT"])

        bad_metadata = self._write_metadata("SampleID\tBatch\nS1\tA\n")
        bad_result = validate_metadata(str(bad_metadata), group_col="Group")

        self.assertEqual(bad_result.status, "failed")
        self.assertIn("Group", bad_result.missing_columns)

    def test_fastq_pairing_detects_pairs_missing_reads_and_extra_files(self) -> None:
        metadata_path = self._write_metadata()
        seq_dir = self.temp_path / "seq"
        seq_dir.mkdir()
        for name in ("S1_1.fq.gz", "S1_2.fq.gz", "S2_1.fq.gz", "S2_2.fq.gz"):
            (seq_dir / name).write_text("", encoding="utf-8")

        result = preview_fastq_pairs(str(metadata_path), str(seq_dir))

        self.assertEqual(result.status, "passed")
        self.assertEqual(result.matched_pairs, 2)
        self.assertTrue(all(pair.status == "ok" for pair in result.pairs))

        (seq_dir / "orphan_1.fq.gz").write_text("", encoding="utf-8")
        warning_result = preview_fastq_pairs(str(metadata_path), str(seq_dir))

        self.assertEqual(warning_result.status, "warning")
        self.assertEqual(len(warning_result.extra_fastq_files), 1)

        (seq_dir / "S2_2.fq.gz").unlink()
        failed_result = preview_fastq_pairs(str(metadata_path), str(seq_dir))

        self.assertEqual(failed_result.status, "failed")
        self.assertEqual(failed_result.pairs[1].status, "missing_r2")

    def test_params_writer_and_command_builder_use_safe_argument_lists(self) -> None:
        metadata_path = self._write_metadata()
        (self.temp_path / "seq").mkdir()
        project = ProjectRecord(
            id="webui-test",
            name="Web UI test",
            project_dir=str(self.temp_path.resolve()),
            output_root="work",
            metadata_path=metadata_path.name,
            seq_dir="seq",
        )

        result = write_pipeline_params(project, PipelineParamsDraft(threads=2))
        params_path = Path(result.params_path)
        written = yaml.safe_load(params_path.read_text(encoding="utf-8"))

        self.assertTrue(params_path.is_file())
        self.assertEqual(result.run_pipeline["threads"], 2)
        self.assertEqual(written["run_pipeline"]["metadata_path"], str(metadata_path.resolve()))

        settings = WebUISettings(python_executable="python")
        command = command_builder.check_pipeline_config(result.params_path, settings)

        self.assertEqual(command.args[0], "python")
        self.assertIn("check-pipeline-config", command.args)
        self.assertIn("--params", command.args)
        self.assertNotIn("&&", command.display)

    def test_result_indexer_finds_plots_reports_and_differential_outputs(self) -> None:
        final_dir = self.temp_path / "work" / "06_final"
        alpha_dir = final_dir / "plots" / "alpha_boxplot_chart"
        alpha_dir.mkdir(parents=True)
        (alpha_dir / "alpha_boxplots.html").write_text("<html></html>", encoding="utf-8")
        (final_dir / "plots" / "index.html").write_text("<html></html>", encoding="utf-8")
        (final_dir / "run_summary.json").write_text("{}", encoding="utf-8")
        (final_dir / "provenance.json").write_text("{}", encoding="utf-8")
        report_dir = final_dir / "report"
        report_dir.mkdir()
        (report_dir / "analysis_report.html").write_text("<html></html>", encoding="utf-8")

        comparison = "KO_vs_WT"
        comparison_dir = final_dir / "statistics" / "differential" / "comparison_result" / comparison
        comparison_dir.mkdir(parents=True)
        (comparison_dir / "differential_results.tsv").write_text("Feature\tlog2FC\nOTU1\t1.5\n", encoding="utf-8")
        (comparison_dir / "differential_results_significant.tsv").write_text(
            "Feature\tlog2FC\nOTU1\t1.5\n",
            encoding="utf-8",
        )
        volcano_dir = final_dir / "statistics" / "differential" / "volcano_chart" / comparison
        heatmap_dir = final_dir / "statistics" / "differential" / "heatmap_chart" / comparison
        volcano_dir.mkdir(parents=True)
        heatmap_dir.mkdir(parents=True)
        (volcano_dir / "volcano.html").write_text("<html></html>", encoding="utf-8")
        (heatmap_dir / "heatmap.html").write_text("<html></html>", encoding="utf-8")

        project = ProjectRecord(
            id="result-test",
            name="Result test",
            project_dir=str(self.temp_path.resolve()),
            output_root="work",
        )
        index = build_result_index(project)

        self.assertTrue(index.available)
        self.assertTrue(index.plots_index)
        self.assertTrue(index.report_html)
        self.assertEqual(len(index.figures["alpha"]), 1)
        self.assertEqual(index.differential[0].comparison, comparison)
        self.assertEqual(index.differential[0].significant_features, 1)

    def test_path_authorization_allows_project_roots_and_rejects_untrusted_paths(self) -> None:
        allowed_path = self._write_metadata()

        preview = read_text_file(str(allowed_path))

        self.assertEqual(preview["name"], allowed_path.name)
        self.assertIn("SampleID", preview["text"])

        outside_root = Path.home() / ".xamplicon_authorized_test"
        outside_path = outside_root / "outside.tsv"

        with self.assertRaises(PermissionError):
            resolve_authorized_path(str(outside_path))

        settings = WebUISettings(authorized_dirs=[str(outside_root)])
        self.assertEqual(resolve_authorized_path(str(outside_path), settings=settings), outside_path.resolve())

    def test_job_manager_runs_short_command_and_records_logs(self) -> None:
        jobs_dir = self.temp_path / "jobs"
        job_manager = JobManager()
        command = CommandSpec(
            args=[sys.executable, "-c", "print('webui-job-ok')"],
            display="short webui job",
            cwd=str(self.temp_path.resolve()),
        )

        with patch("webui.backend.services.job_manager.get_jobs_dir", return_value=jobs_dir):
            record = job_manager.start_job(job_type="smoke", command=command, project_id="project-1")
            deadline = time.time() + 10
            while time.time() < deadline:
                latest = job_manager.get_job(record.id)
                if latest.status in {"completed", "failed", "cancelled"}:
                    break
                time.sleep(0.05)
            else:
                self.fail("Short Web UI job did not finish in time.")

            latest = job_manager.get_job(record.id)
            logs = job_manager.get_logs(record.id)

        self.assertEqual(latest.status, "completed")
        self.assertEqual(latest.return_code, 0)
        self.assertIn("webui-job-ok", logs["text"])


if __name__ == "__main__":
    unittest.main()
