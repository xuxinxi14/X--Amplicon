"""Tests for optional agent skills."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from agent.tools import execute_tool, get_tool_schemas


class AgentSkillTests(unittest.TestCase):
    """Verify skill discovery and basic local skill execution."""

    def setUp(self) -> None:
        self.temp_path = Path("tests") / f"tmp_skill_{uuid4().hex}"
        self.temp_path.mkdir(parents=True, exist_ok=True)
        self.trace_path = self.temp_path / "agent_tool_trace.jsonl"
        self.old_trace_path = os.environ.get("X_AMPLICON_AGENT_TRACE_PATH")
        os.environ["X_AMPLICON_AGENT_TRACE_PATH"] = str(self.trace_path)

    def tearDown(self) -> None:
        if self.old_trace_path is None:
            os.environ.pop("X_AMPLICON_AGENT_TRACE_PATH", None)
        else:
            os.environ["X_AMPLICON_AGENT_TRACE_PATH"] = self.old_trace_path
        rmtree(self.temp_path, ignore_errors=True)

    def test_skill_tools_are_registered(self) -> None:
        names = {schema["function"]["name"] for schema in get_tool_schemas()}

        self.assertIn("search_project_files", names)
        self.assertIn("read_project_file", names)
        self.assertIn("preview_llama_index_documents", names)
        self.assertIn("summarize_agent_traces", names)
        self.assertIn("run_agent_eval_cases", names)
        self.assertIn("inspect_optional_skill_dependencies", names)
        self.assertIn("search_pubmed_literature", names)
        self.assertIn("fetch_pubmed_abstracts", names)

    def test_local_project_rag_tools_execute(self) -> None:
        search_result = execute_tool(
            "search_project_files",
            {"query": "X-Amplicon", "include_patterns": ["*.md"], "max_results": 5},
        )
        self.assertEqual(search_result["status"], "ok", msg=search_result)
        self.assertGreaterEqual(search_result["result"]["result_count"], 1)

        read_result = execute_tool(
            "read_project_file",
            {"path": "README.md", "max_chars": 200},
        )
        self.assertEqual(read_result["status"], "ok", msg=read_result)
        self.assertIn("X-Amplicon", read_result["result"]["content"])

    def test_trace_skill_records_execute_tool_events(self) -> None:
        result = execute_tool("read_project_file", {"path": "README.md", "max_chars": 20})
        self.assertEqual(result["status"], "ok", msg=result)

        summary = execute_tool(
            "summarize_agent_traces",
            {"trace_path": str(self.trace_path), "limit": 5},
        )
        self.assertEqual(summary["status"], "ok", msg=summary)
        payload = summary["result"]
        self.assertGreaterEqual(payload["event_count"], 1)
        self.assertIn("read_project_file", payload["tool_counts"])

    def test_agent_evaluation_static_cases(self) -> None:
        output_path = self.temp_path / "eval_report.json"
        result = execute_tool(
            "run_agent_eval_cases",
            {"output_path": str(output_path)},
        )

        self.assertEqual(result["status"], "ok", msg=result)
        payload = result["result"]
        self.assertEqual(payload["failed_count"], 0, msg=payload)
        self.assertTrue(output_path.is_file())

    def test_optional_dependency_inspection_is_non_failing(self) -> None:
        result = execute_tool("inspect_optional_skill_dependencies", {})

        self.assertEqual(result["status"], "ok", msg=result)
        payload = result["result"]
        self.assertIn("available", payload)
        self.assertIn("biopython", payload["available"])


if __name__ == "__main__":
    unittest.main()
