"""Tests for startup pipeline parameter handling in agent_cli and agent.tools."""

from __future__ import annotations

import unittest
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from agent.state import AgentState
from agent.tools import execute_tool, get_tool_schemas, set_session_pipeline_defaults
from agent.config import AgentConfig
from agent_cli import (
    LANGUAGE_CHINESE,
    LANGUAGE_ENGLISH,
    OfflineAmpliconAgent,
    _build_input_prompt,
    _build_next_actions,
    _build_pipeline_param_rows,
    _build_pipeline_session_context,
    _create_agent_state,
    _extract_pipeline_progress,
    _get_ui_language,
    _handle_slash_command,
    _normalize_language,
    _parse_pipeline_param_value,
    _resolve_history_options,
    _resolve_pipeline_param_key,
    _set_ui_language,
    _summarize_tool_result_for_display,
)
from process import PIPELINE_PARAM_ORDER


class AgentCliPipelineParamTests(unittest.TestCase):
    """Verify startup param parsing helpers used by the interactive agent."""

    def test_parse_pipeline_param_value_converts_numbers_and_optional_none(self) -> None:
        self.assertEqual(_parse_pipeline_param_value("threads", "8"), 8)
        self.assertEqual(_parse_pipeline_param_value("fastq_maxee_rate", "0.01"), 0.01)
        self.assertIsNone(_parse_pipeline_param_value("command_timeout", "none"))

    def test_parse_pipeline_param_value_normalizes_enum_case(self) -> None:
        self.assertEqual(
            _parse_pipeline_param_value("feature_method", "USEARCH-ASV"),
            "usearch-asv",
        )
        self.assertEqual(
            _parse_pipeline_param_value("filter_route", "ITS"),
            "its",
        )

    def test_parse_pipeline_param_value_rejects_invalid_value(self) -> None:
        with self.assertRaises(ValueError):
            _parse_pipeline_param_value("threads", "abc")

        with self.assertRaises(ValueError):
            _parse_pipeline_param_value("feature_method", "bad-method")

    def test_resolve_pipeline_param_key_accepts_index_and_case_insensitive_name(self) -> None:
        params = {key: key for key in PIPELINE_PARAM_ORDER}
        params["beta_tree_path"] = None
        self.assertEqual(_resolve_pipeline_param_key("1", params), PIPELINE_PARAM_ORDER[0])
        self.assertEqual(_resolve_pipeline_param_key("THREADS", params), "threads")
        self.assertIsNone(_resolve_pipeline_param_key("beta_tree_path", params))

    def test_build_pipeline_session_context_includes_path_and_values(self) -> None:
        context = _build_pipeline_session_context(
            "pipeline_params.yaml",
            {
                "metadata_path": "metadata.txt",
                "seq_dir": "seq",
                "output_root": "work",
                "read1_suffix": "_1.fq.gz",
                "read2_suffix": "_2.fq.gz",
                "fastq_stripleft": 29,
                "fastq_stripright": 18,
                "fastq_maxee_rate": 0.01,
                "feature_method": "usearch-asv",
                "feature_minsize": 10,
                "feature_identity": 0.97,
                "chimera_mode": "ref",
                "reference_db": "databas/rdp_16s_v18.fa",
                "otutab_method": "usearch",
                "otutab_identity": 0.97,
                "annotation_database": "rdp_16s_v18",
                "sintax_cutoff": 0.1,
                "filter_route": "16s",
                "beta_tree_path": None,
                "rarefaction_depth": 8000,
                "rarefaction_seed": 1,
                "threads": 16,
                "usearch_path": None,
                "vsearch_path": None,
                "command_timeout": None,
            },
        )
        self.assertIn("pipeline_params.yaml", context)
        self.assertIn('"threads": 16', context)
        self.assertIn('"feature_method": "usearch-asv"', context)
        self.assertIn("run_raw_amplicon_pipeline", context)
        self.assertIn("Do not ask the user to repeat parameters", context)
        self.assertNotIn("beta_tree_path", context)

    def test_build_pipeline_param_rows_marks_edited_and_skipped_optional_values(self) -> None:
        rows = _build_pipeline_param_rows(
            {
                "metadata_path": "metadata.txt",
                "seq_dir": "seq",
                "output_root": "work",
                "read1_suffix": "_1.fq.gz",
                "read2_suffix": "_2.fq.gz",
                "fastq_stripleft": 19,
                "fastq_stripright": 0,
                "fastq_maxee_rate": 0.01,
                "feature_method": "usearch-asv",
                "feature_minsize": 10,
                "feature_identity": 0.97,
                "chimera_mode": "ref",
                "reference_db": "db.fa",
                "otutab_method": "usearch",
                "otutab_identity": 0.97,
                "annotation_database": "rdp_16s_v18",
                "sintax_cutoff": 0.1,
                "filter_route": "16s",
                "rarefaction_depth": 0,
                "rarefaction_seed": 1,
                "threads": 8,
                "usearch_path": None,
                "vsearch_path": None,
                "command_timeout": None,
            },
            baseline_params={
                "metadata_path": "metadata.txt",
                "seq_dir": "seq",
                "output_root": "work",
                "read1_suffix": "_1.fq.gz",
                "read2_suffix": "_2.fq.gz",
                "fastq_stripleft": 19,
                "fastq_stripright": 0,
                "fastq_maxee_rate": 0.01,
                "feature_method": "usearch-asv",
                "feature_minsize": 10,
                "feature_identity": 0.97,
                "chimera_mode": "ref",
                "reference_db": "db.fa",
                "otutab_method": "usearch",
                "otutab_identity": 0.97,
                "annotation_database": "rdp_16s_v18",
                "sintax_cutoff": 0.1,
                "filter_route": "16s",
                "rarefaction_depth": 0,
                "rarefaction_seed": 1,
                "threads": 4,
                "usearch_path": "old-usearch.exe",
                "vsearch_path": None,
                "command_timeout": None,
            },
        )

        rows_by_name = {row["name"]: row for row in rows}
        self.assertEqual(rows_by_name["threads"]["state"], "Edited")
        self.assertEqual(rows_by_name["usearch_path"]["state"], "Edited")
        self.assertIn("YAML:", rows_by_name["usearch_path"]["note"])
        self.assertNotIn("beta_tree_path", rows_by_name)

    def test_build_pipeline_param_rows_separates_value_state_from_validation(self) -> None:
        rows = _build_pipeline_param_rows(
            {
                "metadata_path": "metadata.txt",
                "seq_dir": "seq",
                "output_root": "work",
                "read1_suffix": "_1.fq.gz",
                "read2_suffix": "_2.fq.gz",
                "fastq_stripleft": 19,
                "fastq_stripright": 0,
                "fastq_maxee_rate": 0.01,
                "feature_method": "usearch-asv",
                "feature_minsize": 10,
                "feature_identity": 0.97,
                "chimera_mode": "ref",
                "reference_db": "db.fa",
                "otutab_method": "usearch",
                "otutab_identity": 0.97,
                "annotation_database": "rdp_16s_v18",
                "sintax_cutoff": 0.1,
                "filter_route": "16s",
                "rarefaction_depth": 0,
                "rarefaction_seed": 1,
                "threads": 8,
                "usearch_path": "bin/windows/usearch.exe",
                "vsearch_path": "bin/windows/vsearch.exe",
                "command_timeout": None,
            },
            validation_report={
                "checks": [
                    {
                        "name": "metadata",
                        "status": "failed",
                        "message": "metadata_path not found: metadata.txt",
                    },
                    {
                        "name": "usearch_executable",
                        "status": "passed",
                        "message": "USEARCH executable is available.",
                    },
                ]
            },
        )

        rows_by_name = {row["name"]: row for row in rows}
        self.assertEqual(rows_by_name["metadata_path"]["state"], "Set")
        self.assertEqual(rows_by_name["metadata_path"]["validation"], "Issue")
        self.assertIn("metadata_path not found", rows_by_name["metadata_path"]["note"])
        self.assertEqual(rows_by_name["usearch_path"]["validation"], "Validated")
        self.assertNotIn("beta_tree_path", rows_by_name)

    def test_run_pipeline_tool_schema_hides_beta_tree_path(self) -> None:
        schemas = get_tool_schemas()
        run_schema = next(
            schema
            for schema in schemas
            if schema["function"]["name"] == "run_raw_amplicon_pipeline"
        )
        properties = run_schema["function"]["parameters"]["properties"]

        self.assertNotIn("beta_tree_path", properties)


class AgentToolSessionDefaultTests(unittest.TestCase):
    """Verify session defaults are applied to the full pipeline tool."""

    def tearDown(self) -> None:
        set_session_pipeline_defaults(None)

    def test_execute_tool_merges_session_pipeline_defaults(self) -> None:
        captured: dict[str, object] = {}

        def fake_pipeline(**kwargs):
            captured.update(kwargs)
            return {"received": kwargs}

        with patch("agent.tools.get_tool_map", return_value={"run_raw_amplicon_pipeline": fake_pipeline}):
            set_session_pipeline_defaults(
                {
                    "metadata_path": "metadata.txt",
                    "seq_dir": "seq",
                    "output_root": "work",
                    "fastq_stripleft": 29,
                    "fastq_stripright": 18,
                    "fastq_maxee_rate": 0.01,
                    "threads": 16,
                }
            )
            result = execute_tool(
                "run_raw_amplicon_pipeline",
                {
                    "output_root": "custom-work",
                },
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(captured["metadata_path"], "metadata.txt")
        self.assertEqual(captured["seq_dir"], "seq")
        self.assertEqual(captured["output_root"], "custom-work")
        self.assertEqual(captured["threads"], 16)

    def test_execute_tool_normalizes_blank_optional_pipeline_paths(self) -> None:
        captured: dict[str, object] = {}

        def fake_pipeline(**kwargs):
            captured.update(kwargs)
            return {"received": kwargs}

        with patch("agent.tools.get_tool_map", return_value={"run_raw_amplicon_pipeline": fake_pipeline}):
            set_session_pipeline_defaults(
                {
                    "metadata_path": "metadata.txt",
                    "seq_dir": "seq",
                    "output_root": "work",
                    "fastq_stripleft": 29,
                    "fastq_stripright": 18,
                    "fastq_maxee_rate": 0.01,
                    "beta_tree_path": "",
                    "usearch_path": "",
                    "vsearch_path": "   ",
                }
            )
            result = execute_tool("run_raw_amplicon_pipeline", {})

        self.assertEqual(result["status"], "ok")
        self.assertIsNone(captured["beta_tree_path"])
        self.assertIsNone(captured["usearch_path"])
        self.assertIsNone(captured["vsearch_path"])

    def test_execute_tool_normalizes_placeholder_optional_pipeline_paths(self) -> None:
        captured: dict[str, object] = {}

        def fake_pipeline(**kwargs):
            captured.update(kwargs)
            return {"received": kwargs}

        with patch("agent.tools.get_tool_map", return_value={"run_raw_amplicon_pipeline": fake_pipeline}):
            set_session_pipeline_defaults(
                {
                    "metadata_path": "metadata.txt",
                    "seq_dir": "seq",
                    "output_root": "work",
                    "fastq_stripleft": 29,
                    "fastq_stripright": 18,
                    "fastq_maxee_rate": 0.01,
                    "beta_tree_path": "tree.nwk",
                    "usearch_path": "none",
                    "vsearch_path": "null",
                    "command_timeout": None,
                }
            )
            result = execute_tool(
                "run_raw_amplicon_pipeline",
                {"beta_tree_path": "none", "command_timeout": 0},
            )

        self.assertEqual(result["status"], "ok")
        self.assertIsNone(captured["beta_tree_path"])
        self.assertIsNone(captured["usearch_path"])
        self.assertIsNone(captured["vsearch_path"])
        self.assertIsNone(captured["command_timeout"])

    def test_execute_tool_normalizes_beta_tree_skip_markers(self) -> None:
        for placeholder in [".", "/__skip_unifrac__", "_SKIP_UNIFRAC_", ","]:
            with self.subTest(placeholder=placeholder):
                captured: dict[str, object] = {}

                def fake_pipeline(**kwargs):
                    captured.update(kwargs)
                    return {"received": kwargs}

                with patch("agent.tools.get_tool_map", return_value={"run_raw_amplicon_pipeline": fake_pipeline}):
                    set_session_pipeline_defaults(
                        {
                            "metadata_path": "metadata.txt",
                            "seq_dir": "seq",
                            "output_root": "work",
                            "fastq_stripleft": 29,
                            "fastq_stripright": 18,
                            "fastq_maxee_rate": 0.01,
                            "beta_tree_path": None,
                        }
                    )
                    result = execute_tool(
                        "run_raw_amplicon_pipeline",
                        {"beta_tree_path": placeholder},
                    )

                self.assertEqual(result["status"], "ok")
                self.assertIsNone(captured["beta_tree_path"])

    def test_execute_tool_reports_missing_metadata_without_executable_hint(self) -> None:
        def fake_pipeline(**kwargs):
            raise FileNotFoundError("metadata_path not found: D:\\missing\\metadata.txt")

        with patch("agent.tools.get_tool_map", return_value={"run_raw_amplicon_pipeline": fake_pipeline}):
            result = execute_tool("run_raw_amplicon_pipeline", {})

        self.assertEqual(result["status"], "error")
        self.assertIn("metadata_path", result["error"])
        self.assertNotIn("USEARCH or VSEARCH", result["error"])

    def test_execute_tool_reports_missing_executable_with_executable_hint(self) -> None:
        def fake_pipeline(**kwargs):
            raise FileNotFoundError("USEARCH executable not found: D:\\tools\\usearch.exe")

        with patch("agent.tools.get_tool_map", return_value={"run_raw_amplicon_pipeline": fake_pipeline}):
            result = execute_tool("run_raw_amplicon_pipeline", {})

        self.assertEqual(result["status"], "error")
        self.assertIn("USEARCH or VSEARCH", result["error"])


class AgentCliStateTests(unittest.TestCase):
    """Verify default fresh sessions and explicit resume behavior."""

    def test_agent_config_treats_example_api_key_as_missing(self) -> None:
        temp_path = Path("tests") / f"tmp_agent_config_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            env_path = temp_path / ".env"
            env_path.write_text(
                "LLM_API_KEY=sk-your-actual-key-here\nDEFAULT_MODEL=gpt-4o\n",
                encoding="utf-8",
            )

            with patch.dict("os.environ", {}, clear=True):
                config = AgentConfig(env_file=str(env_path))

            self.assertEqual(config.api_key, "")
            with self.assertRaises(ValueError):
                config.validate()
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_create_agent_state_starts_fresh_without_resume(self) -> None:
        temp_path = Path("tests") / f"tmp_agent_state_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            state_path = temp_path / "agent_state.json"
            existing_state = AgentState(str(state_path))
            existing_state.add_message("user", "old question")
            existing_state.add_message("assistant", "old answer")

            args = SimpleNamespace(state=str(state_path), resume=False, reset=False)
            with patch("agent_cli.console.print"):
                state = _create_agent_state(args)

            self.assertEqual(state.get_messages(), [])
            self.assertEqual(state.get_tool_results(), [])
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_create_agent_state_resumes_saved_history_with_resume_flag(self) -> None:
        temp_path = Path("tests") / f"tmp_agent_state_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            state_path = temp_path / "agent_state.json"
            existing_state = AgentState(str(state_path))
            existing_state.add_message("user", "old question")
            existing_state.add_message("assistant", "old answer")

            args = SimpleNamespace(state=str(state_path), resume=True, reset=False)
            with patch("agent_cli.console.print"):
                state = _create_agent_state(args)

            self.assertEqual(len(state.get_messages()), 2)
            self.assertEqual(state.get_messages()[0]["content"], "old question")
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_offline_agent_records_user_turn_without_llm(self) -> None:
        temp_path = Path("tests") / f"tmp_agent_state_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            state = AgentState(str(temp_path / "agent_state.json"), autoload=False)
            agent = OfflineAmpliconAgent(
                config=AgentConfig(api_key="", env_file=str(temp_path / "missing.env")),
                state=state,
                reason="missing key",
            )

            reply = agent.chat("run my analysis")

            self.assertIn("CLI", reply)
            self.assertIn("cli-only-workflow", reply)
            messages = state.get_messages()
            self.assertEqual(messages[0]["role"], "user")
            self.assertEqual(messages[1]["role"], "assistant")
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_agent_state_loads_preferences_without_resuming_history(self) -> None:
        temp_path = Path("tests") / f"tmp_agent_state_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            state_path = temp_path / "agent_state.json"
            existing_state = AgentState(str(state_path))
            existing_state.set_preference("language", LANGUAGE_CHINESE)
            existing_state.add_message("user", "old question")

            state = AgentState(str(state_path), autoload=False)

            self.assertEqual(state.get_messages(), [])
            self.assertEqual(state.get_preference("language"), LANGUAGE_CHINESE)
        finally:
            rmtree(temp_path, ignore_errors=True)


class AgentCliSlashCommandTests(unittest.TestCase):
    """Verify slash commands that manage session pipeline params."""

    def tearDown(self) -> None:
        _set_ui_language(LANGUAGE_ENGLISH)

    def test_normalize_language_accepts_common_aliases(self) -> None:
        self.assertEqual(_normalize_language("Chinese"), LANGUAGE_CHINESE)
        self.assertEqual(_normalize_language("中文"), LANGUAGE_CHINESE)
        self.assertEqual(_normalize_language("zh"), LANGUAGE_CHINESE)
        self.assertEqual(_normalize_language("English"), LANGUAGE_ENGLISH)
        self.assertEqual(_normalize_language("en"), LANGUAGE_ENGLISH)
        self.assertIsNone(_normalize_language("Klingon"))

    def test_handle_slash_language_inline_persists_preference(self) -> None:
        preferences: dict[str, str] = {}

        class FakeState:
            state_path = "tests/tmp_state.json"
            startup_mode = "fresh"
            startup_note = ""

            def get_messages(self) -> list[dict[str, str]]:
                return []

            def get_tool_results(self) -> list[dict[str, object]]:
                return []

            def set_preference(self, key: str, value: str) -> None:
                preferences[key] = value

        agent = SimpleNamespace(
            state=FakeState(),
            session_pipeline_params=None,
            session_pipeline_params_path=None,
        )

        with patch("agent_cli.console.print"):
            handled = _handle_slash_command("/language Chinese", agent)

        self.assertTrue(handled)
        self.assertEqual(_get_ui_language(), LANGUAGE_CHINESE)
        self.assertEqual(preferences["language"], LANGUAGE_CHINESE)

    def test_handle_slash_language_prompts_when_no_inline_value(self) -> None:
        preferences: dict[str, str] = {}

        class FakeState:
            state_path = "tests/tmp_state.json"
            startup_mode = "fresh"
            startup_note = ""

            def get_messages(self) -> list[dict[str, str]]:
                return []

            def get_tool_results(self) -> list[dict[str, object]]:
                return []

            def set_preference(self, key: str, value: str) -> None:
                preferences[key] = value

        agent = SimpleNamespace(
            state=FakeState(),
            session_pipeline_params=None,
            session_pipeline_params_path=None,
        )

        with (
            patch("agent_cli.console.print"),
            patch("agent_cli.console.input", return_value="English") as input_mock,
        ):
            _set_ui_language(LANGUAGE_CHINESE)
            handled = _handle_slash_command("/language", agent)

        self.assertTrue(handled)
        input_mock.assert_called_once()
        self.assertEqual(_get_ui_language(), LANGUAGE_ENGLISH)
        self.assertEqual(preferences["language"], LANGUAGE_ENGLISH)

    def test_handle_slash_params_applies_confirmed_defaults(self) -> None:
        agent = SimpleNamespace(
            session_pipeline_params_path="pipeline_params.yaml",
            session_pipeline_params={"threads": 1},
            session_context=None,
        )

        with (
            patch(
                "agent_cli._confirm_pipeline_params",
                return_value=({"threads": 16}, "context"),
            ) as confirm_mock,
            patch("agent_cli._apply_session_pipeline_params") as apply_mock,
            patch("agent_cli.console.print"),
        ):
            handled = _handle_slash_command("/params", agent)

        self.assertTrue(handled)
        confirm_mock.assert_called_once_with(
            "pipeline_params.yaml",
            current_params={"threads": 1},
            confirm_message="Session pipeline params updated.",
            skip_message="Session pipeline params unchanged.",
        )
        apply_mock.assert_called_once_with(agent, "pipeline_params.yaml", {"threads": 16})

    def test_handle_slash_params_keeps_defaults_when_cancelled(self) -> None:
        agent = SimpleNamespace(
            session_pipeline_params_path="pipeline_params.yaml",
            session_pipeline_params={"threads": 1},
            session_context=None,
        )

        with (
            patch(
                "agent_cli._confirm_pipeline_params",
                return_value=(None, None),
            ),
            patch("agent_cli._apply_session_pipeline_params") as apply_mock,
        ):
            handled = _handle_slash_command("/params", agent)

        self.assertTrue(handled)
        apply_mock.assert_not_called()

    def test_handle_slash_status_dispatches_to_status_view(self) -> None:
        agent = SimpleNamespace()

        with patch("agent_cli._cmd_status") as status_mock:
            handled = _handle_slash_command("/status", agent)

        self.assertTrue(handled)
        status_mock.assert_called_once_with(agent)

    def test_handle_slash_help_dispatches_to_help_view(self) -> None:
        agent = SimpleNamespace()

        with patch("agent_cli._cmd_help") as help_mock:
            handled = _handle_slash_command("/help", agent)

        self.assertTrue(handled)
        help_mock.assert_called_once_with(agent)


class AgentCliDisplayHelperTests(unittest.TestCase):
    """Verify timeline summaries and next-step suggestion helpers."""

    def test_extract_pipeline_progress_reports_current_step_and_counts(self) -> None:
        progress = _extract_pipeline_progress(
            {
                "status": "running",
                "sample_ids": ["S1", "S2"],
                "steps": [
                    {"name": "validate_inputs", "status": "completed"},
                    {
                        "name": "merge_pairs",
                        "status": "in_progress",
                        "description": "Merge paired-end FASTQ files sample by sample.",
                    },
                ],
            }
        )

        self.assertEqual(progress["completed_steps"], 1)
        self.assertEqual(progress["started_steps"], 2)
        self.assertEqual(progress["current_step"], "merge_pairs")
        self.assertEqual(progress["sample_count"], 2)
        self.assertIn("current: merge_pairs", progress["summary"])

    def test_resolve_history_options_supports_role_and_limit(self) -> None:
        role_filter, limit = _resolve_history_options("/history tool 8")
        self.assertEqual(role_filter, "tool")
        self.assertEqual(limit, 8)

    def test_summarize_tool_result_for_display_reads_pipeline_summary(self) -> None:
        temp_path = Path("tests") / f"tmp_agent_cli_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            summary_path = temp_path / "run_summary.json"
            summary_path.write_text(
                '{"sample_ids":["S1","S2"],"effective_params":{"feature_method":"usearch-asv"},"outputs":{"analysis_outputs":{"generated_beta_metrics":["braycurtis"],"skipped_beta_metrics":["weighted_unifrac"]}}}',
                encoding="utf-8",
            )

            summary = _summarize_tool_result_for_display(
                "run_raw_amplicon_pipeline",
                {
                    "status": "ok",
                    "result": {"summary_path": str(summary_path)},
                },
            )
        finally:
            rmtree(temp_path, ignore_errors=True)

        self.assertIn("2 sample(s)", summary)
        self.assertIn("feature_method=usearch-asv", summary)

    def test_build_next_actions_prioritizes_report_after_pipeline_success(self) -> None:
        agent = SimpleNamespace(
            session_pipeline_params={"threads": 8},
            state=SimpleNamespace(get_completed_steps=lambda: ["run_raw_amplicon_pipeline"]),
        )
        actions = _build_next_actions(
            agent,
            [
                {
                    "name": "run_raw_amplicon_pipeline",
                    "status": "ok",
                    "summary": "pipeline ok",
                    "result": {"result": {}},
                }
            ],
        )

        self.assertIn("/report to export a Markdown summary of this run.", actions)
        self.assertIn("/history to review the session trace in dialogue form.", actions)

    def test_build_input_prompt_includes_mode_and_param_state(self) -> None:
        agent = SimpleNamespace(
            state=SimpleNamespace(startup_mode="fresh"),
            session_pipeline_params={"threads": 8},
        )

        prompt = _build_input_prompt(agent)

        self.assertIn("FRESH", prompt)
        self.assertIn("PARAMS OK", prompt)


if __name__ == "__main__":
    unittest.main()
