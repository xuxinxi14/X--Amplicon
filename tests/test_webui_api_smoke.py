"""Smoke tests for the X-Amplicon Web UI FastAPI app."""

from __future__ import annotations

import unittest
import json
from pathlib import Path
from shutil import rmtree
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from webui.backend.app import app
from webui.backend.models.common import CommandSpec
from webui.backend.models.job import JobRecord


class FakeJobManager:
    """Return completed-looking job records without starting subprocesses."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.started: list[tuple[str, CommandSpec, str | None, str]] = []
        self.records: dict[str, JobRecord] = {}

    def start_job(
        self,
        *,
        job_type: str,
        command: CommandSpec,
        project_id: str | None = None,
        initial_status: str = "queued",
    ) -> JobRecord:
        self.started.append((job_type, command, project_id, initial_status))
        record = JobRecord(
            id=f"{job_type}-smoke",
            project_id=project_id,
            job_type=job_type,
            status="completed" if job_type == "preflight" else initial_status,  # type: ignore[arg-type]
            command=command.args,
            display_command=command.display,
            cwd=command.cwd,
            log_path=str(self.state_dir / f"{job_type}.log"),
            event_path=str(self.state_dir / f"{job_type}.events.jsonl"),
            message="Smoke job created.",
        )
        self.records[record.id] = record
        return record

    def start_sequence_job(
        self,
        *,
        job_type: str,
        commands: list[tuple[str, CommandSpec]],
        project_id: str | None = None,
        initial_status: str = "queued",
    ) -> JobRecord:
        first_command = commands[0][1]
        display = "\n".join(f"{stage}: {command.display}" for stage, command in commands)
        self.started.append((job_type, first_command, project_id, initial_status))
        record = JobRecord(
            id=f"{job_type}-smoke",
            project_id=project_id,
            job_type=job_type,
            status=initial_status,  # type: ignore[arg-type]
            command=first_command.args,
            display_command=display,
            cwd=first_command.cwd,
            log_path=str(self.state_dir / f"{job_type}.log"),
            event_path=str(self.state_dir / f"{job_type}.events.jsonl"),
            message="Smoke sequence job created.",
        )
        self.records[record.id] = record
        return record

    def get_job(self, job_id: str) -> JobRecord:
        if job_id not in self.records:
            raise KeyError(f"Job not found: {job_id}")
        return self.records[job_id]


class WebUIApiSmokeTests(unittest.TestCase):
    """Exercise key API endpoints against isolated local state."""

    def setUp(self) -> None:
        self.temp_path = Path("tests") / f"tmp_webui_api_{uuid4().hex}"
        self.project_dir = self.temp_path / "project"
        self.state_dir = self.temp_path / "state"
        self.jobs_dir = self.state_dir / "jobs"
        self.seq_dir = self.project_dir / "seq"
        self.seq_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        (self.project_dir / "metadata.tsv").write_text("SampleID\tGroup\nS1\tWT\nS2\tKO\n", encoding="utf-8")
        for name in ("S1_1.fq.gz", "S1_2.fq.gz", "S2_1.fq.gz", "S2_2.fq.gz"):
            (self.seq_dir / name).write_text("", encoding="utf-8")

        self.patchers = [
            patch("webui.backend.services.project_store.ensure_state_dir", return_value=self.state_dir),
            patch("webui.backend.services.settings_store.ensure_state_dir", return_value=self.state_dir),
            patch("webui.backend.services.job_manager.get_jobs_dir", return_value=self.jobs_dir),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        for patcher in reversed(self.patchers):
            patcher.stop()
        rmtree(self.temp_path, ignore_errors=True)

    def _create_project(self) -> dict[str, object]:
        response = self.client.post(
            "/api/projects",
            json={
                "name": "Smoke Project",
                "project_dir": str(self.project_dir.resolve()),
                "output_root": "work",
            },
        )
        self.assertEqual(response.status_code, 200, msg=response.text)
        return response.json()

    def _write_job(self, project_id: str | None, status: str = "completed") -> JobRecord:
        job_id = f"job-{uuid4().hex[:8]}"
        job = JobRecord(
            id=job_id,
            project_id=project_id,
            job_type="full_analysis",
            status=status,  # type: ignore[arg-type]
            log_path=str(self.jobs_dir / f"{job_id}.log"),
            event_path=str(self.jobs_dir / f"{job_id}.events.jsonl"),
        )
        (self.jobs_dir / f"{job.id}.json").write_text(job.model_dump_json(), encoding="utf-8")
        (self.jobs_dir / f"{job.id}.log").write_text("log", encoding="utf-8")
        (self.jobs_dir / f"{job.id}.events.jsonl").write_text("{}", encoding="utf-8")
        return job

    def test_health_settings_projects_validation_pairing_job_and_results_endpoints(self) -> None:
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

        settings = self.client.get("/api/settings")
        self.assertEqual(settings.status_code, 200)
        self.assertIn(settings.json()["language"], {"Chinese", "English"})

        self.assertEqual(self.client.get("/api/projects").json(), [])
        project = self._create_project()
        project_id = str(project["id"])

        metadata = self.client.post(
            f"/api/projects/{project_id}/validate-metadata",
            json={"metadata_path": "metadata.tsv", "sample_id_col": "SampleID", "group_col": "Group"},
        )
        self.assertEqual(metadata.status_code, 200, msg=metadata.text)
        self.assertEqual(metadata.json()["status"], "passed")

        pairing = self.client.post(
            f"/api/projects/{project_id}/preview-pairs",
            json={"metadata_path": "metadata.tsv", "seq_dir": "seq"},
        )
        self.assertEqual(pairing.status_code, 200, msg=pairing.text)
        self.assertEqual(pairing.json()["matched_pairs"], 2)

        params = self.client.post(f"/api/projects/{project_id}/write-params", json={})
        self.assertEqual(params.status_code, 200, msg=params.text)
        self.assertTrue(Path(params.json()["params_path"]).is_file())

        final_dir = self.project_dir / "work" / "06_final" / "plots"
        final_dir.mkdir(parents=True)
        (final_dir / "index.html").write_text("<html></html>", encoding="utf-8")
        results = self.client.get(f"/api/results/{project_id}")
        self.assertEqual(results.status_code, 200, msg=results.text)
        self.assertTrue(results.json()["available"])
        self.assertTrue(results.json()["plots_index"])

        fake_manager = FakeJobManager(self.state_dir)
        with patch("webui.backend.api.projects.manager", fake_manager):
            job = self.client.post(f"/api/projects/{project_id}/preflight")

        self.assertEqual(job.status_code, 200, msg=job.text)
        self.assertEqual(job.json()["job_type"], "preflight")
        self.assertEqual(fake_manager.started[0][0], "preflight")
        self.assertIn("check-pipeline-config", fake_manager.started[0][1].args)

        with patch("webui.backend.api.projects.manager", fake_manager):
            run_job = self.client.post(f"/api/projects/{project_id}/run")

        self.assertEqual(run_job.status_code, 200, msg=run_job.text)
        self.assertEqual(run_job.json()["job_type"], "full_analysis")
        self.assertIn("run-pipeline-config", run_job.json()["display_command"])
        self.assertIn("visualization-suite", run_job.json()["display_command"])
        self.assertIn("--format all", run_job.json()["display_command"])
        self.assertIn("generate-report", run_job.json()["display_command"])

    def test_full_analysis_requires_completed_preflight(self) -> None:
        project = self._create_project()
        project_id = str(project["id"])
        configured = self.client.put(
            f"/api/projects/{project_id}",
            json={"metadata_path": "metadata.tsv", "seq_dir": "seq"},
        )
        self.assertEqual(configured.status_code, 200, msg=configured.text)
        params = self.client.post(f"/api/projects/{project_id}/write-params", json={})
        self.assertEqual(params.status_code, 200, msg=params.text)

        fake_manager = FakeJobManager(self.state_dir)
        with patch("webui.backend.api.projects.manager", fake_manager):
            run_job = self.client.post(f"/api/projects/{project_id}/run")

        self.assertEqual(run_job.status_code, 409, msg=run_job.text)
        self.assertIn("Preflight must complete", run_job.text)
        self.assertEqual(fake_manager.started, [])

    def test_project_history_delete_endpoints_keep_outputs_untouched(self) -> None:
        project = self._create_project()
        project_id = str(project["id"])
        job = self._write_job(project_id)
        output_file = self.project_dir / "work" / "06_final" / "run_summary.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("{}", encoding="utf-8")

        deleted = self.client.delete(f"/api/projects/{project_id}")
        self.assertEqual(deleted.status_code, 204, msg=deleted.text)
        self.assertEqual(self.client.get("/api/projects").json(), [])
        self.assertTrue(output_file.is_file())
        self.assertFalse((self.jobs_dir / f"{job.id}.json").exists())
        self.assertFalse((self.jobs_dir / f"{job.id}.log").exists())
        self.assertFalse((self.jobs_dir / f"{job.id}.events.jsonl").exists())

        second_project = self._create_project()
        self._write_job(str(second_project["id"]))
        cleared = self.client.delete("/api/projects")
        self.assertEqual(cleared.status_code, 200, msg=cleared.text)
        self.assertEqual(cleared.json()["deleted"], 1)
        self.assertEqual(cleared.json()["deleted_jobs"], 1)
        self.assertEqual(self.client.get("/api/projects").json(), [])
        self.assertEqual(self.client.get("/api/jobs").json(), [])

    def test_project_history_delete_blocks_active_jobs(self) -> None:
        project = self._create_project()
        project_id = str(project["id"])
        self._write_job(project_id, status="running")

        deleted = self.client.delete(f"/api/projects/{project_id}")
        self.assertEqual(deleted.status_code, 409, msg=deleted.text)
        self.assertEqual(len(self.client.get("/api/projects").json()), 1)

        cleared = self.client.delete("/api/projects")
        self.assertEqual(cleared.status_code, 409, msg=cleared.text)
        self.assertEqual(len(self.client.get("/api/jobs").json()), 1)

    def test_job_progress_endpoint_reads_summary_and_returns_404_for_missing_job(self) -> None:
        project = self._create_project()
        project_id = str(project["id"])
        job = self._write_job(project_id, status="running")
        Path(job.event_path).write_text(
            json.dumps(
                {
                    "time": "2026-01-01T00:00:00+00:00",
                    "stage": "job",
                    "status": "running",
                    "details": {"steps": ["pipeline", "visualization", "report"]},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        summary_path = self.project_dir / "work" / "06_final" / "run_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(
                {
                    "status": "running",
                    "current_step": "merge_pairs",
                    "failed_step": None,
                    "steps": [
                        {"name": "validate_inputs", "status": "completed"},
                        {"name": "merge_pairs", "status": "in_progress"},
                    ],
                }
            ),
            encoding="utf-8",
        )

        response = self.client.get(f"/api/jobs/{job.id}/progress")
        self.assertEqual(response.status_code, 200, msg=response.text)
        payload = response.json()
        self.assertEqual(payload["current_step"], "merge_pairs")
        self.assertIn("validate_inputs", [step["key"] for step in payload["steps"]])
        self.assertIn("visualization", [step["key"] for step in payload["steps"]])

        missing = self.client.get("/api/jobs/not-found/progress")
        self.assertEqual(missing.status_code, 404)

    def test_table_export_endpoint_validates_inputs_and_returns_images(self) -> None:
        project = self._create_project()
        project_id = str(project["id"])
        table_path = self.project_dir / "work" / "06_final" / "alpha_diversity.tsv"
        table_path.parent.mkdir(parents=True, exist_ok=True)
        table_path.write_text("SampleID\tShannon\nS1\t3.1\nS2\t2.8\n", encoding="utf-8")

        with patch("plotly.io.to_image", return_value=b"IMAGE"):
            for export_format, media_type in (
                ("png", "image/png"),
                ("svg", "image/svg+xml"),
                ("pdf", "application/pdf"),
            ):
                response = self.client.get(
                    "/api/files/table-export",
                    params={"path": str(table_path), "format": export_format, "project_id": project_id},
                )
                self.assertEqual(response.status_code, 200, msg=response.text)
                self.assertEqual(response.content, b"IMAGE")
                self.assertIn(media_type, response.headers["content-type"])

        invalid_format = self.client.get(
            "/api/files/table-export",
            params={"path": str(table_path), "format": "jpg", "project_id": project_id},
        )
        self.assertEqual(invalid_format.status_code, 400)
        self.assertIn("Table export format", invalid_format.text)

        markdown_path = self.project_dir / "notes.md"
        markdown_path.write_text("# notes\n", encoding="utf-8")
        non_table = self.client.get(
            "/api/files/table-export",
            params={"path": str(markdown_path), "format": "png", "project_id": project_id},
        )
        self.assertEqual(non_table.status_code, 400)
        self.assertIn("Only TSV", non_table.text)

        unauthorized = self.client.get(
            "/api/files/table-export",
            params={"path": str(Path.home() / f"untrusted_{uuid4().hex}.tsv"), "format": "png", "project_id": project_id},
        )
        self.assertEqual(unauthorized.status_code, 403)

        with patch("plotly.io.to_image", side_effect=ValueError("Image export requires Kaleido")):
            missing_kaleido = self.client.get(
                "/api/files/table-export",
                params={"path": str(table_path), "format": "png", "project_id": project_id},
            )
        self.assertEqual(missing_kaleido.status_code, 400)
        self.assertIn("Kaleido may be missing", missing_kaleido.text)

    def test_agent_and_current_results_endpoints_are_lightweight(self) -> None:
        llm_settings = self.client.get("/api/settings/llm")
        self.assertEqual(llm_settings.status_code, 200, msg=llm_settings.text)
        self.assertNotIn("api_key", llm_settings.json())
        self.assertIn("api_key_configured", llm_settings.json())

        agent_status = self.client.get("/api/agent/status")
        self.assertEqual(agent_status.status_code, 200, msg=agent_status.text)
        self.assertIn("llm_available", agent_status.json())

        explanation = self.client.post(
            "/api/agent/explain",
            json={
                "question": "Metadata validation failed. What should I check?",
                "technical_text": "Missing columns: SampleID, Group",
                "prefer_llm": False,
            },
        )
        self.assertEqual(explanation.status_code, 200, msg=explanation.text)
        self.assertEqual(explanation.json()["mode"], "rule_based")
        self.assertTrue(explanation.json()["summary"])

        chat = self.client.post(
            "/api/agent/chat",
            json={
                "messages": [{"role": "user", "content": "我想开始完整 16S 分析"}],
                "language": "Chinese",
                "prefer_llm": False,
            },
        )
        self.assertEqual(chat.status_code, 200, msg=chat.text)
        self.assertEqual(chat.json()["mode"], "rule_based")
        self.assertIn("新建分析", chat.json()["message"])
        self.assertIn("创建项目", chat.json()["message"])
        self.assertIn("metadata", chat.json()["message"])
        self.assertIn("preflight", chat.json()["message"])

        current_results = self.client.get("/api/results/current")
        self.assertEqual(current_results.status_code, 200, msg=current_results.text)
        self.assertEqual(current_results.json()["project_id"], "current")


if __name__ == "__main__":
    unittest.main()
