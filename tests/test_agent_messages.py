"""Tests for agent message construction and state summarization."""

from __future__ import annotations

import unittest
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from agent.agent import AmpliconAgent, MAX_REPLAY_MESSAGES
from agent.config import AgentConfig
from agent.state import AgentState


class AgentMessageConstructionTests(unittest.TestCase):
    """Verify the agent replays recent turns and summarizes older state."""

    def test_build_messages_uses_structured_summary_and_recent_history_window(self) -> None:
        temp_path = Path("tests") / f"tmp_agent_messages_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            state = AgentState(str(temp_path / "agent_state.json"), autoload=False)
            for index in range(MAX_REPLAY_MESSAGES + 3):
                state.add_message("user", f"user {index}")
                state.add_message("assistant", f"assistant {index}")

            state.record_tool_result(
                "run_raw_amplicon_pipeline",
                {"seq_dir": "seq"},
                {"status": "error", "error": "beta_tree_path is required."},
            )

            agent = AmpliconAgent(
                config=AgentConfig(model="test-model", api_key="test-key"),
                state=state,
                verbose=False,
            )
            agent.set_session_pipeline_params(
                params_path="pipeline_params.yaml",
                params={"threads": 16},
                context="confirmed defaults",
            )

            messages = agent._build_messages()

            replay_messages = [
                message
                for message in messages
                if message["role"] in ("user", "assistant")
            ]
            system_text = "\n".join(
                message["content"]
                for message in messages
                if message["role"] == "system"
            )

            self.assertEqual(len(replay_messages), MAX_REPLAY_MESSAGES)
            self.assertEqual(replay_messages[0]["content"], "user 7")
            self.assertEqual(replay_messages[-1]["content"], "assistant 10")
            self.assertIn("Structured session summary:", system_text)
            self.assertIn("Confirmed session pipeline defaults are active", system_text)
            self.assertIn("Older conversation messages omitted from verbatim replay", system_text)
            self.assertIn("run_raw_amplicon_pipeline: error; beta_tree_path is required.", system_text)
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_build_messages_warns_when_session_defaults_are_not_confirmed(self) -> None:
        temp_path = Path("tests") / f"tmp_agent_messages_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            state = AgentState(str(temp_path / "agent_state.json"), autoload=False)
            state.add_message("user", "quickly analyze my data")
            state.add_message("assistant", "need parameters")

            agent = AmpliconAgent(
                config=AgentConfig(model="test-model", api_key="test-key"),
                state=state,
                verbose=False,
            )

            system_text = "\n".join(
                message["content"]
                for message in agent._build_messages()
                if message["role"] == "system"
            )

            self.assertIn("No confirmed session pipeline defaults are active", system_text)
            self.assertIn("do not assume values from pipeline_params.yaml are in effect", system_text.lower())
        finally:
            rmtree(temp_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
