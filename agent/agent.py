"""Core agent loop: Perception → Reasoning → Action → Observation.

Uses LiteLLM to call any OpenAI-compatible LLM endpoint with function calling.
API key, base URL, and model are resolved from AgentConfig (env vars / .env file).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any

os.environ.setdefault("LITELLM_LOG", "ERROR")

import litellm

from agent.config import AgentConfig
from agent.state import AgentState
from agent.tools import execute_tool, get_tool_schemas

litellm.suppress_debug_info = True
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
try:
    litellm._disable_debugging()
except AttributeError:
    pass

SYSTEM_PROMPT = """You are an expert 16S rRNA amplicon analysis assistant.
You have access to a suite of bioinformatics tools that cover the full
X-Amplicon pipeline: raw FASTQ processing, OTU/ASV generation, taxonomy
annotation, alpha diversity, beta diversity, abundance filtering, and
visualization.
You also have optional agent skills for local project retrieval, tool-call
tracing, static agent evaluation, and PubMed literature retrieval. Use local
project retrieval when the user asks about repository files, run summaries, or
generated artifacts. Use tracing and evaluation tools for debugging or
measuring agent behavior. Use literature retrieval only when the user asks for
source-backed biomedical context, references, or evidence, and report source
metadata such as PubMed IDs when available.

When the user asks you to perform an analysis step, call the appropriate tool.
If session defaults have already been confirmed, treat them as ready-to-use
inputs. For requests like "quickly analyze my data", "start analysis", "run
the pipeline", or similar, call the relevant pipeline tool directly instead of
asking the user to repeat confirmed parameters.
If session defaults have not been confirmed, do not invent pipeline arguments
or claim to be using pipeline_params.yaml automatically. Before calling the
full raw pipeline, require either confirmed session defaults or explicit
user-provided required inputs.
After a successful full pipeline run, or when the user asks for plots from an
existing completed run, call run_visualization_suite unless the user only wants
numeric tables or interpretation without generating files. By default, write
visualizations to work/06_final/plots and prefer offline HTML output.
Treat validated tool results and structured session summaries as more reliable
than older assistant wording from prior turns.
For optional file paths, omit the argument or use null; never send an empty
string, ".", "none", "null", or invented skip markers as placeholder paths.
When a tool returns an error about a missing executable (USEARCH/VSEARCH),
report the error clearly and suggest the user provide the executable path.
Always explain what you did and what the result means in plain language after
each tool call.
"""

MAX_TOOL_ROUNDS = 10
MAX_REPLAY_MESSAGES = 8
MAX_SUMMARIZED_TOOL_RESULTS = 5


class AmpliconAgent:
    """Minimal Viable Agent for 16S amplicon analysis.

    Args:
        config: AgentConfig with resolved model, api_key, and api_base.
            If not provided, one is created from environment / .env file.
        state: AgentState instance for persistence. A fresh one is created
            if not provided.
        verbose: Print tool call details to stdout when True.
    """

    def __init__(
        self,
        config: AgentConfig | None = None,
        state: AgentState | None = None,
        verbose: bool = True,
        session_context: str | None = None,
    ) -> None:
        self.config = config or AgentConfig()
        self.state = state or AgentState()
        self.verbose = verbose
        self.session_context = session_context
        self.session_pipeline_params_path: str | None = None
        self.session_pipeline_params: dict[str, Any] | None = None
        self._tools = get_tool_schemas()

    # kept for callers that pass model as a positional/keyword arg
    @classmethod
    def from_model(
        cls,
        model: str,
        state: AgentState | None = None,
        verbose: bool = True,
    ) -> "AmpliconAgent":
        """Convenience constructor that accepts a bare model string.

        Args:
            model: LiteLLM model string (e.g. 'gpt-4o', 'claude-sonnet-4-6').
            state: Optional AgentState.
            verbose: Print tool call details when True.

        Returns:
            A new AmpliconAgent with the given model and env-resolved credentials.
        """
        return cls(config=AgentConfig(model=model), state=state, verbose=verbose)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(self, user_message: str) -> str:
        """Process one user turn and return the assistant's final reply.

        Implements the Perception → Reasoning → Action → Observation loop.
        Tool calls are executed and fed back to the model until the model
        produces a plain text reply or MAX_TOOL_ROUNDS is reached.

        Args:
            user_message: The user's natural-language request.

        Returns:
            The assistant's final text response for this turn.
        """
        task_id = uuid.uuid4().hex
        task_start_time = time.perf_counter()
        turn_index = 0
        round_count = 0
        tool_call_count = 0
        tool_error_count = 0
        tool_error_types: set[str] = set()
        recovery_paths: set[str] = set()
        task_status = "failed"
        failure_reason: str | None = None
        reply_text: str | None = None

        try:
            self.state.add_message("user", user_message)
            turn_index = sum(
                1 for message in self.state.get_messages() if message.get("role") == "user"
            )
            messages = self._build_messages()

            completion_kwargs: dict[str, Any] = {
                "model": self.config.model,
                "messages": messages,
                "tools": self._tools,
            }
            if self.config.api_key:
                completion_kwargs["api_key"] = self.config.api_key
            if self.config.api_base:
                completion_kwargs["api_base"] = self.config.api_base

            for round_index in range(MAX_TOOL_ROUNDS):
                round_count = round_index + 1
                # Reasoning
                completion_kwargs["messages"] = messages
                response = litellm.completion(**completion_kwargs)

                choice = response.choices[0]
                assistant_msg = choice.message
                tool_calls = assistant_msg.tool_calls or []

                if not tool_calls:
                    reply_text = assistant_msg.content or ""
                    self.state.add_message("assistant", reply_text)
                    task_status = "success"
                    return reply_text

                # Action
                messages.append(assistant_msg.model_dump(exclude_none=True))

                for tool_call in tool_calls:
                    tool_call_count += 1
                    tool_name = tool_call.function.name
                    try:
                        arguments: dict[str, Any] = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    if self.verbose:
                        print(f"\n[Agent] Calling tool: {tool_name}")
                        print(f"[Agent] Arguments: {json.dumps(arguments, indent=2, default=str)}")

                    # Observation
                    result = execute_tool(tool_name, arguments)
                    self.state.record_tool_result(tool_name, arguments, result)

                    if result.get("status") == "error":
                        tool_error_count += 1
                        error_text = str(result.get("error", ""))
                        self._collect_error_classification(
                            error_text,
                            tool_error_types=tool_error_types,
                            recovery_paths=recovery_paths,
                        )

                    if self.verbose:
                        if result.get("status") == "ok":
                            print(f"[Agent] Tool '{tool_name}' succeeded.")
                        else:
                            print(f"[Agent] Tool '{tool_name}' failed: {result.get('error')}")

                    observation_content = json.dumps(result, default=str)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": observation_content,
                        }
                    )
                    self.state.add_message("tool", observation_content)

            fallback = (
                "I reached the maximum number of tool-call rounds without a final answer. "
                "Please check the tool results above and try a more specific request."
            )
            reply_text = fallback
            failure_reason = fallback
            task_status = "max_rounds"
            self.state.add_message("assistant", fallback)
            return fallback
        except Exception as exc:
            task_status = "failed"
            failure_reason = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._record_task_evaluation(
                task_id=task_id,
                user_message=user_message,
                status=task_status,
                start_time=task_start_time,
                turn_index=turn_index,
                round_count=round_count,
                tool_call_count=tool_call_count,
                tool_error_count=tool_error_count,
                failure_reason=failure_reason,
                assistant_reply=reply_text,
                error_types=sorted(tool_error_types),
                recovery_paths=sorted(recovery_paths),
            )

    def reset(self) -> None:
        """Clear conversation history and tool results."""
        self.state.reset()

    def set_session_context(self, context: str | None) -> None:
        """Replace the current session-scoped system context."""

        self.session_context = context

    def set_session_pipeline_params(
        self,
        *,
        params_path: str | None,
        params: dict[str, Any] | None,
        context: str | None = None,
    ) -> None:
        """Replace the current session-scoped pipeline defaults."""

        self.session_pipeline_params_path = (
            None if params_path is None else os.path.abspath(params_path)
        )
        self.session_pipeline_params = None if params is None else dict(params)
        self.session_context = context

    def _collect_error_classification(
        self,
        error_text: str,
        *,
        tool_error_types: set[str],
        recovery_paths: set[str],
    ) -> None:
        """Collect best-effort error labels for task-level evaluation."""

        try:
            from agent.evaluation_logger import classify_error
        except Exception:  # noqa: BLE001
            return

        try:
            classification = classify_error(error_text)
        except Exception:  # noqa: BLE001
            return

        error_type = classification.get("error_type")
        recovery_path = classification.get("recovery_path")
        if error_type:
            tool_error_types.add(str(error_type))
        if recovery_path:
            recovery_paths.add(str(recovery_path))

    def _record_task_evaluation(
        self,
        *,
        task_id: str,
        user_message: str,
        status: str,
        start_time: float,
        turn_index: int,
        round_count: int,
        tool_call_count: int,
        tool_error_count: int,
        failure_reason: str | None,
        assistant_reply: str | None,
        error_types: list[str],
        recovery_paths: list[str],
    ) -> None:
        """Write best-effort task-level evaluation data."""

        try:
            from agent.evaluation_logger import record_task_evaluation_event
        except Exception:  # noqa: BLE001
            return

        try:
            event = record_task_evaluation_event(
                task_id=task_id,
                user_message=user_message,
                status=status,
                start_time=start_time,
                turn_index=turn_index,
                round_count=round_count,
                tool_call_count=tool_call_count,
                tool_error_count=tool_error_count,
                failure_reason=failure_reason,
                assistant_reply=assistant_reply,
                model=self.config.model,
                llm_available=bool(self.config.api_key),
                error_types=error_types,
                recovery_paths=recovery_paths,
            )
        except Exception:  # noqa: BLE001
            return

        try:
            self.state.record_task_result(event)
        except Exception:  # noqa: BLE001
            return

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(self) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        if self.session_context:
            messages.append({"role": "system", "content": self.session_context})
        state_summary = self._build_state_summary()
        if state_summary:
            messages.append({"role": "system", "content": state_summary})

        replay_messages = [
            msg
            for msg in self.state.get_messages()
            if msg["role"] in ("user", "assistant")
        ]
        for msg in replay_messages[-MAX_REPLAY_MESSAGES:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        return messages

    def _build_state_summary(self) -> str | None:
        replay_messages = [
            msg
            for msg in self.state.get_messages()
            if msg["role"] in ("user", "assistant")
        ]
        tool_results = self.state.get_tool_results()
        completed_steps = self.state.get_completed_steps()

        if not replay_messages and not tool_results and not completed_steps:
            return None

        summary_lines = [
            "Structured session summary:",
            "- Prefer this summary and recent tool outcomes over older assistant wording.",
        ]

        omitted_messages = max(0, len(replay_messages) - MAX_REPLAY_MESSAGES)
        if omitted_messages:
            summary_lines.append(
                f"- Older conversation messages omitted from verbatim replay: {omitted_messages}."
            )

        if self.session_pipeline_params is not None:
            summary_lines.append(
                "- Confirmed session pipeline defaults are active and can be used immediately."
            )
        else:
            summary_lines.append(
                "- No confirmed session pipeline defaults are active. Do not assume values from pipeline_params.yaml are in effect."
            )

        if completed_steps:
            summary_lines.append(
                "- Completed tools so far: " + ", ".join(completed_steps[-MAX_SUMMARIZED_TOOL_RESULTS:]) + "."
            )

        if tool_results:
            summary_lines.append("- Recent tool outcomes:")
            for record in tool_results[-MAX_SUMMARIZED_TOOL_RESULTS:]:
                summary_lines.append(f"  * {self._summarize_tool_result(record)}")

        return "\n".join(summary_lines)

    def _summarize_tool_result(self, record: dict[str, Any]) -> str:
        tool_name = str(record.get("tool", "unknown_tool"))
        result = record.get("result", {})
        if not isinstance(result, dict):
            return f"{tool_name}: result unavailable."

        status = result.get("status")
        if status == "ok":
            payload = result.get("result")
            if isinstance(payload, dict):
                output_keys = ", ".join(sorted(payload.keys())[:5])
                if output_keys:
                    return f"{tool_name}: ok; returned keys [{output_keys}]."
            return f"{tool_name}: ok."

        error = str(result.get("error", "unknown error"))
        compact_error = " ".join(error.split())
        if len(compact_error) > 180:
            compact_error = compact_error[:177] + "..."
        return f"{tool_name}: error; {compact_error}"
