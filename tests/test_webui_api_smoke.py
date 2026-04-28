"""Smoke tests for the X-Amplicon Web UI FastAPI app."""

from __future__ import annotations

import unittest
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

    def start_job(
        self,
        *,
        job_type: str,
        command: CommandSpec,
        project_id: str | None = None,
        initial_status: str = "queued",
    ) -> JobRecord:
        self.started.append((job_type, command, project_id, initial_status))
        return JobRecord(
            id=f"{job_type}-smoke",
            project_id=project_id,
            job_type=job_type,
            status=initial_status,  # type: ignore[arg-type]
            command=command.args,
            display_command=command.display,
            cwd=command.cwd,
            log_path=str(self.state_dir / f"{job_type}.log"),
            event_path=str(self.state_dir / f"{job_type}.events.jsonl"),
            message="Smoke job created.",
        )


class WebUIApiSmokeTests(unittest.TestCase):
    """Exercise key API endpoints against isolated local state."""

    def setUp(self) -> None:
        self.temp_path = Path("tests") / f"tmp_webui_api_{uuid4().hex}"
        self.project_dir = self.temp_path / "project"
        self.state_dir = self.temp_path / "state"
        self.seq_dir = self.project_dir / "seq"
        self.seq_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.project_dir / "metadata.tsv").write_text("SampleID\tGroup\nS1\tWT\nS2\tKO\n", encoding="utf-8")
        for name in ("S1_1.fq.gz", "S1_2.fq.gz", "S2_1.fq.gz", "S2_2.fq.gz"):
            (self.seq_dir / name).write_text("", encoding="utf-8")

        self.patchers = [
            patch("webui.backend.services.project_store.ensure_state_dir", return_value=self.state_dir),
            patch("webui.backend.services.settings_store.ensure_state_dir", return_value=self.state_dir),
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

        current_results = self.client.get("/api/results/current")
        self.assertEqual(current_results.status_code, 200, msg=current_results.text)
        self.assertEqual(current_results.json()["project_id"], "current")


if __name__ == "__main__":
    unittest.main()
