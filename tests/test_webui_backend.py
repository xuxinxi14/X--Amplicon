"""Unit tests for Web UI backend services."""

from __future__ import annotations

import sys
import time
import unittest
import json
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import yaml

from webui.backend.models.agent import AgentChatRequest, AgentStatusResponse
from webui.backend.models.common import CommandSpec
from webui.backend.models.job import JobRecord
from webui.backend.models.project import PipelineParamsDraft, ProjectRecord
from webui.backend.models.settings import WebUISettings
from webui.backend.services import command_builder
from webui.backend.services.agent_help_service import (
    _commands_for_context,
    _llm_chat,
    _load_webui_guidance_skill,
    _safe_json_response,
)
from webui.backend.services.fastq_pairing import preview_fastq_pairs
from webui.backend.services.file_service import read_text_file, resolve_authorized_path, rewrite_html_links_for_file_view
from webui.backend.services.job_manager import JobManager, _terminate_process_tree
from webui.backend.services.job_progress import build_job_progress
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

    def _progress_job(self, job_type: str = "full_analysis", status: str = "running") -> JobRecord:
        job_id = f"{job_type}-{uuid4().hex[:8]}"
        return JobRecord(
            id=job_id,
            project_id="progress-project",
            job_type=job_type,
            status=status,  # type: ignore[arg-type]
            log_path=str(self.temp_path / f"{job_id}.log"),
            event_path=str(self.temp_path / f"{job_id}.events.jsonl"),
            message="Progress test job.",
        )

    def _write_events(self, job: JobRecord, events: list[dict[str, object]]) -> None:
        Path(job.event_path).write_text(
            "\n".join(json.dumps(event) for event in events) + "\n",
            encoding="utf-8",
        )

    def _write_run_summary(self, project: ProjectRecord, payload: dict[str, object] | str) -> Path:
        summary_path = Path(project.project_dir) / project.output_root / "06_final" / "run_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            summary_path.write_text(payload, encoding="utf-8")
        else:
            summary_path.write_text(json.dumps(payload), encoding="utf-8")
        return summary_path

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
        self.assertTrue(result.messages)
        self.assertTrue(all(pair.status == "ok" for pair in result.pairs))

        (seq_dir / "orphan_1.fq.gz").write_text("", encoding="utf-8")
        warning_result = preview_fastq_pairs(str(metadata_path), str(seq_dir))

        self.assertEqual(warning_result.status, "warning")
        self.assertEqual(len(warning_result.extra_fastq_files), 1)
        self.assertTrue(warning_result.messages)
        self.assertTrue(warning_result.suggestions)

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
        self.assertEqual(result.run_pipeline["merge_backend"], "vsearch")
        self.assertEqual(written["run_pipeline"]["metadata_path"], str(metadata_path.resolve()))
        self.assertEqual(written["run_pipeline"]["merge_backend"], "vsearch")

        settings = WebUISettings(python_executable="python")
        command = command_builder.check_pipeline_config(result.params_path, settings)

        self.assertEqual(command.args[0], "python")
        self.assertIn("check-pipeline-config", command.args)
        self.assertIn("--params", command.args)
        self.assertNotIn("&&", command.display)

        viz_command = command_builder.visualization_suite(
            str(self.temp_path / "work" / "06_final"),
            metadata=str(metadata_path),
            sample_id_col="SampleID",
            group_col="Group",
            settings=settings,
        )
        self.assertIn("visualization-suite", viz_command.args)
        self.assertEqual(viz_command.args[viz_command.args.index("--format") + 1], "all")
        self.assertIn("--sample-id-col", viz_command.args)
        self.assertIn("--group-col", viz_command.args)

        diff_command = command_builder.differential_abundance(
            otutab=str(self.temp_path / "work" / "06_final" / "otutab.txt"),
            metadata=str(metadata_path),
            output_dir=str(self.temp_path / "work" / "06_final" / "statistics" / "differential"),
            comparisons=["KO:WT"],
            settings=settings,
        )
        self.assertIn("--output-dir", diff_command.args)
        self.assertIn("--compare", diff_command.args)

    def test_agent_fallback_commands_match_cli_options(self) -> None:
        result_commands = _commands_for_context("results")
        diff_commands = _commands_for_context("differential")

        self.assertIn("--final-dir", result_commands[0])
        self.assertNotIn("--output-root", result_commands[0])
        self.assertIn("--otutab", diff_commands[0])
        self.assertIn("--compare", diff_commands[0])
        self.assertNotIn("--otu-table", diff_commands[0])
        self.assertNotIn("--comparisons", diff_commands[0])

    def test_windows_cancel_uses_process_tree_termination(self) -> None:
        class FakeProcess:
            pid = 1234
            terminated = False

            def terminate(self) -> None:
                self.terminated = True

        process = FakeProcess()
        with patch("webui.backend.services.job_manager.os.name", "nt"), patch(
            "webui.backend.services.job_manager.subprocess.run"
        ) as run:
            _terminate_process_tree(process)  # type: ignore[arg-type]

        run.assert_called_once()
        self.assertFalse(process.terminated)

    def test_result_indexer_finds_plots_reports_and_differential_outputs(self) -> None:
        final_dir = self.temp_path / "work8" / "06_final"
        alpha_dir = final_dir / "plots" / "alpha_boxplot_chart"
        alpha_dir.mkdir(parents=True)
        (alpha_dir / "alpha_boxplots.html").write_text("<html></html>", encoding="utf-8")
        (alpha_dir / "alpha_boxplots.png").write_bytes(b"png")
        (alpha_dir / "alpha_boxplots.svg").write_text("<svg></svg>", encoding="utf-8")
        beta_dir = final_dir / "plots" / "beta_pcoa_chart"
        beta_dir.mkdir(parents=True)
        (beta_dir / "beta_pcoa_braycurtis.png").write_bytes(b"png")
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
        (volcano_dir / "volcano.pdf").write_bytes(b"pdf")
        (heatmap_dir / "heatmap.html").write_text("<html></html>", encoding="utf-8")
        (heatmap_dir / "heatmap.svg").write_text("<svg></svg>", encoding="utf-8")

        project = ProjectRecord(
            id="result-test",
            name="Result test",
            project_dir=str(self.temp_path.resolve()),
            output_root="work8",
        )
        index = build_result_index(project)

        self.assertTrue(index.available)
        self.assertTrue(index.plots_index)
        self.assertTrue(index.report_html)
        self.assertEqual(len(index.figures["alpha"]), 1)
        self.assertEqual(index.figures["alpha"][0].formats["html"], str((alpha_dir / "alpha_boxplots.html").resolve()))
        self.assertEqual(index.figures["alpha"][0].formats["png"], str((alpha_dir / "alpha_boxplots.png").resolve()))
        self.assertEqual(index.figures["beta"][0].path, str((beta_dir / "beta_pcoa_braycurtis.png").resolve()))
        self.assertEqual(index.differential[0].comparison, comparison)
        self.assertEqual(index.differential[0].significant_features, 1)
        self.assertIn("pdf", index.differential[0].volcano_formats)
        self.assertIn("svg", index.differential[0].heatmap_formats)

    def test_job_progress_falls_back_to_job_record_without_events(self) -> None:
        job = self._progress_job(status="running")

        with patch("webui.backend.services.job_progress.get_project", side_effect=KeyError("missing")):
            progress = build_job_progress(job)

        self.assertEqual(progress.status, "running")
        self.assertEqual(progress.steps[0].key, "full_analysis")
        self.assertEqual(progress.steps[0].status, "running")
        self.assertTrue(progress.warnings)

    def test_job_progress_uses_sequence_events_for_webui_stages(self) -> None:
        job = self._progress_job()
        self._write_events(
            job,
            [
                {
                    "time": "2026-01-01T00:00:00+00:00",
                    "stage": "job",
                    "status": "running",
                    "details": {"steps": ["pipeline", "visualization", "report"]},
                },
                {"time": "2026-01-01T00:00:01+00:00", "stage": "pipeline", "status": "running"},
                {"time": "2026-01-01T00:00:02+00:00", "stage": "pipeline", "status": "completed"},
                {"time": "2026-01-01T00:00:03+00:00", "stage": "visualization", "status": "running"},
            ],
        )

        with patch("webui.backend.services.job_progress.get_project", side_effect=KeyError("missing")):
            progress = build_job_progress(job)

        statuses = {step.key: step.status for step in progress.steps}
        self.assertEqual(statuses["pipeline"], "completed")
        self.assertEqual(statuses["visualization"], "running")
        self.assertEqual(statuses["report"], "pending")
        self.assertEqual(progress.current_step, "visualization")

    def test_job_progress_uses_run_summary_for_pipeline_steps(self) -> None:
        job = self._progress_job()
        project = ProjectRecord(
            id=job.project_id or "progress-project",
            name="Progress project",
            project_dir=str(self.temp_path.resolve()),
            output_root="work",
        )
        self._write_events(
            job,
            [
                {
                    "time": "2026-01-01T00:00:00+00:00",
                    "stage": "job",
                    "status": "running",
                    "details": {"steps": ["pipeline", "visualization", "report"]},
                }
            ],
        )
        self._write_run_summary(
            project,
            {
                "status": "running",
                "current_step": "merge_pairs",
                "failed_step": None,
                "steps": [
                    {
                        "name": "validate_inputs",
                        "description": "Validate required inputs.",
                        "status": "completed",
                    },
                    {
                        "name": "merge_pairs",
                        "description": "Merge paired-end FASTQ files.",
                        "status": "in_progress",
                    },
                ],
            },
        )

        with patch("webui.backend.services.job_progress.get_project", return_value=project):
            progress = build_job_progress(job)

        statuses = {step.key: step.status for step in progress.steps}
        self.assertEqual(progress.current_step, "merge_pairs")
        self.assertEqual(statuses["validate_inputs"], "completed")
        self.assertEqual(statuses["merge_pairs"], "running")
        self.assertEqual(statuses["filter_reads"], "pending")
        self.assertEqual(statuses["visualization"], "pending")

    def test_job_progress_reports_failed_run_summary_step(self) -> None:
        job = self._progress_job(status="failed")
        project = ProjectRecord(
            id=job.project_id or "progress-project",
            name="Progress project",
            project_dir=str(self.temp_path.resolve()),
            output_root="work",
        )
        self._write_run_summary(
            project,
            {
                "status": "failed",
                "current_step": "filter_reads",
                "failed_step": "filter_reads",
                "error": "quality filtering failed",
                "steps": [
                    {"name": "validate_inputs", "status": "completed"},
                    {"name": "filter_reads", "status": "failed", "error": "quality filtering failed"},
                ],
            },
        )

        with patch("webui.backend.services.job_progress.get_project", return_value=project):
            progress = build_job_progress(job)

        statuses = {step.key: step.status for step in progress.steps}
        self.assertEqual(progress.failed_step, "filter_reads")
        self.assertIn("quality filtering failed", progress.message)
        self.assertEqual(statuses["filter_reads"], "failed")

    def test_job_progress_tolerates_malformed_run_summary(self) -> None:
        job = self._progress_job()
        project = ProjectRecord(
            id=job.project_id or "progress-project",
            name="Progress project",
            project_dir=str(self.temp_path.resolve()),
            output_root="work",
        )
        self._write_events(job, [{"stage": "pipeline", "status": "running"}])
        self._write_run_summary(project, "{not-json")

        with patch("webui.backend.services.job_progress.get_project", return_value=project):
            progress = build_job_progress(job)

        self.assertEqual(progress.steps[0].key, "pipeline")
        self.assertEqual(progress.steps[0].status, "running")
        self.assertTrue(progress.warnings)

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

    def test_html_file_view_rewrites_relative_report_links(self) -> None:
        final_dir = self.temp_path / "work" / "06_final"
        report_dir = final_dir / "report"
        plots_dir = final_dir / "plots"
        report_dir.mkdir(parents=True)
        plots_dir.mkdir(parents=True)
        (plots_dir / "index.html").write_text("<html>plots</html>", encoding="utf-8")
        source = report_dir / "analysis_report.html"
        source.write_text(
            '<iframe src="../plots/index.html"></iframe>'
            '<a href="../plots/index.html#top">plot</a>'
            '<a href="https://example.org">external</a>'
            '<script>const template = \'<a href="../plots/index.html">plot</a>\';</script>'
            '<script src="/assets/app.js"></script>',
            encoding="utf-8",
        )

        rewritten = rewrite_html_links_for_file_view(source.read_text(encoding="utf-8"), source_path=source)

        self.assertIn("/api/files/view?path=", rewritten)
        self.assertIn("plots%5Cindex.html", rewritten)
        self.assertIn("#top", rewritten)
        self.assertIn('href="https://example.org"', rewritten)
        self.assertIn('const template = \'<a href="../plots/index.html">plot</a>\';', rewritten)
        self.assertIn('src="/assets/app.js"', rewritten)

    def test_agent_json_response_extraction_handles_wrapped_llm_output(self) -> None:
        parsed = _safe_json_response(
            '```json\n{"message":"Start from New Analysis.","suggested_actions":["Create project"]}\n```'
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["message"], "Start from New Analysis.")

        wrapped = _safe_json_response(
            'I will answer below.\n{"broken": }\n{"message":"ok","suggested_actions":[],"suggested_commands":[],"warnings":[]}'
        )

        self.assertIsNotNone(wrapped)
        self.assertEqual(wrapped["message"], "ok")

    def test_webui_guidance_skill_loads_key_page_names(self) -> None:
        guide = _load_webui_guidance_skill()

        for page_name in ("Agent 助手", "新建分析", "运行监控", "结果", "数据库", "设置"):
            self.assertIn(page_name, guide)

    def test_llm_chat_prompt_includes_webui_guidance_skill(self) -> None:
        captured: dict[str, object] = {}

        def fake_completion(**kwargs: object) -> object:
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='{"message":"ok","suggested_actions":[],"suggested_commands":[],"warnings":[]}'
                        )
                    )
                ]
            )

        status = AgentStatusResponse(
            status="online",
            llm_available=True,
            key_configured=True,
            model="openai/gpt-5.5",
            api_base_configured=True,
            provider="openai-compatible",
            message="ok",
        )
        request = AgentChatRequest(
            messages=[{"role": "user", "content": "我想开始完整 16S 分析"}],
            language="Chinese",
            prefer_llm=True,
        )

        with patch.dict(sys.modules, {"litellm": SimpleNamespace(completion=fake_completion)}):
            with patch("webui.backend.services.agent_help_service.get_agent_status", return_value=status):
                _llm_chat(request)

        prompt_text = "\n".join(
            str(message.get("content", ""))
            for message in captured["messages"]  # type: ignore[index, union-attr]
        )
        self.assertIn("webui_guidance_skill", prompt_text)
        self.assertIn("必须包含：进入`新建分析`", prompt_text)

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

    def test_job_manager_runs_sequence_job_and_records_step_logs(self) -> None:
        jobs_dir = self.temp_path / "jobs"
        job_manager = JobManager()
        commands = [
            (
                "first",
                CommandSpec(
                    args=[sys.executable, "-c", "print('sequence-one')"],
                    display="sequence first",
                    cwd=str(self.temp_path.resolve()),
                ),
            ),
            (
                "second",
                CommandSpec(
                    args=[sys.executable, "-c", "print('sequence-two')"],
                    display="sequence second",
                    cwd=str(self.temp_path.resolve()),
                ),
            ),
        ]

        with patch("webui.backend.services.job_manager.get_jobs_dir", return_value=jobs_dir):
            record = job_manager.start_sequence_job(job_type="sequence", commands=commands, project_id="project-1")
            deadline = time.time() + 10
            while time.time() < deadline:
                latest = job_manager.get_job(record.id)
                if latest.status in {"completed", "failed", "cancelled"}:
                    break
                time.sleep(0.05)
            else:
                self.fail("Short Web UI sequence job did not finish in time.")

            latest = job_manager.get_job(record.id)
            logs = job_manager.get_logs(record.id)

        self.assertEqual(latest.status, "completed")
        self.assertEqual(latest.return_code, 0)
        self.assertIn("sequence-one", logs["text"])
        self.assertIn("sequence-two", logs["text"])


if __name__ == "__main__":
    unittest.main()
