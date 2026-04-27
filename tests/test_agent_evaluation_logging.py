"""Tests for Agent evaluation JSONL logging."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from agent.agent import AmpliconAgent
from agent.config import AgentConfig
from agent.evaluation_logger import (
    append_evaluation_event,
    classify_error,
    read_evaluation_events,
    summarize_evaluation_log,
)
from agent.state import AgentState
from agent.tools import execute_tool, set_session_pipeline_defaults


class AgentEvaluationLoggerTests(unittest.TestCase):
    """Verify evaluation events for tool calls, user tasks, and exports."""

    def setUp(self) -> None:
        self.temp_path = Path("tests") / f"tmp_agent_eval_{uuid4().hex}"
        self.temp_path.mkdir(parents=True, exist_ok=True)
        self.eval_log = (self.temp_path / "agent_evaluation_log.jsonl").resolve()
        self.trace_log = (self.temp_path / "agent_tool_trace.jsonl").resolve()

    def tearDown(self) -> None:
        set_session_pipeline_defaults(None)
        rmtree(self.temp_path, ignore_errors=True)

    def _log_env(self) -> dict[str, str]:
        return {
            "X_AMPLICON_AGENT_EVAL_LOG_PATH": str(self.eval_log),
            "X_AMPLICON_AGENT_TRACE_PATH": str(self.trace_log),
        }

    def test_classify_error_labels_common_recovery_paths(self) -> None:
        self.assertEqual(
            classify_error("metadata_path not found: missing.txt")["error_type"],
            "missing_metadata",
        )
        self.assertEqual(
            classify_error("VSEARCH executable not found: bin/vsearch.exe")["recovery_path"],
            "configure_external_executable",
        )
        self.assertEqual(
            classify_error("beta_tree_path not found: bad.tree")["error_type"],
            "bad_tree_path",
        )

    def test_execute_tool_writes_tool_call_evaluation_event(self) -> None:
        def fake_pipeline(**kwargs):
            raise FileNotFoundError("metadata_path not found: D:\\missing\\metadata.txt")

        with (
            patch.dict(os.environ, self._log_env(), clear=False),
            patch("agent.tools.get_tool_map", return_value={"run_raw_amplicon_pipeline": fake_pipeline}),
        ):
            result = execute_tool("run_raw_amplicon_pipeline", {"output_root": "work"})

        self.assertEqual(result["status"], "error")
        events = read_evaluation_events(str(self.eval_log))
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["event_type"], "tool_call")
        self.assertEqual(event["tool"], "run_raw_amplicon_pipeline")
        self.assertEqual(event["status"], "error")
        self.assertEqual(event["error_type"], "missing_metadata")
        self.assertEqual(event["recovery_path"], "confirm_metadata_path")
        self.assertIn("arguments", event)
        self.assertIn("result", event)

    def test_amplicon_agent_chat_writes_user_task_event(self) -> None:
        state = AgentState(str(self.temp_path / "agent_state.json"), autoload=False)
        agent = AmpliconAgent(
            config=AgentConfig(
                model="openai/test-model",
                api_key="test-key",
                env_file=str(self.temp_path / "missing.env"),
            ),
            state=state,
            verbose=False,
        )
        fake_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(tool_calls=None, content="analysis finished")
                )
            ]
        )

        with (
            patch.dict(os.environ, self._log_env(), clear=False),
            patch("agent.agent.litellm.completion", return_value=fake_response),
        ):
            reply = agent.chat("summarize the current run")

        self.assertEqual(reply, "analysis finished")
        events = read_evaluation_events(str(self.eval_log))
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["event_type"], "user_task")
        self.assertEqual(event["status"], "success")
        self.assertEqual(event["round_count"], 1)
        self.assertEqual(event["tool_call_count"], 0)
        self.assertEqual(event["tool_error_count"], 0)
        self.assertFalse(event["recovery_required"])
        self.assertEqual(state.get_task_results()[0]["status"], "success")

    def test_summary_and_export_agent_evaluation_log(self) -> None:
        append_evaluation_event(
            {
                "event_id": "task-1",
                "event_type": "user_task",
                "status": "success",
                "duration_seconds": 0.1,
            },
            log_path=str(self.eval_log),
        )
        append_evaluation_event(
            {
                "event_id": "tool-1",
                "event_type": "tool_call",
                "tool": "run_raw_amplicon_pipeline",
                "status": "error",
                "duration_seconds": 0.2,
                "error_type": "missing_executable",
                "recovery_path": "configure_external_executable",
            },
            log_path=str(self.eval_log),
        )

        from agent.skills.agent_evaluation.tools import (
            export_agent_evaluation_log,
            summarize_agent_evaluation_log,
        )

        summary = summarize_agent_evaluation_log(log_path=str(self.eval_log), limit=5)
        self.assertEqual(summary["event_count"], 2)
        self.assertEqual(summary["task_count"], 1)
        self.assertEqual(summary["tool_call_count"], 1)
        self.assertEqual(summary["error_type_counts"]["missing_executable"], 1)

        output_path = self.temp_path / "export.json"
        exported = export_agent_evaluation_log(
            output_path=str(output_path),
            log_path=str(self.eval_log),
        )
        self.assertEqual(exported["event_count"], 2)
        self.assertTrue(output_path.is_file())


if __name__ == "__main__":
    unittest.main()
