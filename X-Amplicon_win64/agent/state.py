"""Lightweight JSON-backed state management for the 16S analysis agent.

Persists conversation history, tool call results, and analysis progress
to a single JSON file so sessions can be resumed after interruption.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any


DEFAULT_STATE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "run_logs", "agent_state.json"
)


class AgentState:
    """Manages agent state: conversation history, tool results, and progress.

    Args:
        state_path: Path to the JSON file used for persistence.
            Defaults to run_logs/agent_state.json relative to the project root.
        autoload: When True, load an existing state file automatically.
    """

    def __init__(
        self,
        state_path: str = DEFAULT_STATE_PATH,
        *,
        autoload: bool = True,
    ) -> None:
        self.state_path = os.path.abspath(state_path)
        self._data: dict[str, Any] = {
            "conversation": [],
            "tool_results": [],
            "task_results": [],
            "completed_steps": [],
            "preferences": {},
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        if os.path.isfile(self.state_path):
            if autoload:
                self._load()
            else:
                self._load_preferences()

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    def add_message(self, role: str, content: str) -> None:
        """Append a message to the conversation history.

        Args:
            role: One of 'user', 'assistant', or 'tool'.
            content: Message text or serialised tool result.
        """
        self._data["conversation"].append({"role": role, "content": content})
        self._touch()

    def get_messages(self) -> list[dict[str, str]]:
        """Return the full conversation history.

        Returns:
            List of dicts with 'role' and 'content' keys.
        """
        return list(self._data["conversation"])

    # ------------------------------------------------------------------
    # Tool results
    # ------------------------------------------------------------------

    def record_tool_result(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        """Record a tool execution and its outcome.

        Args:
            tool_name: Name of the tool that was called.
            arguments: Arguments passed to the tool.
            result: Structured result dict returned by execute_tool.
        """
        self._data["tool_results"].append(
            {
                "tool": tool_name,
                "arguments": arguments,
                "result": result,
                "timestamp": time.time(),
            }
        )
        if result.get("status") == "ok":
            if tool_name not in self._data["completed_steps"]:
                self._data["completed_steps"].append(tool_name)
        self._touch()

    def get_tool_results(self) -> list[dict[str, Any]]:
        """Return all recorded tool results.

        Returns:
            List of tool result records ordered by execution time.
        """
        return list(self._data["tool_results"])

    def get_completed_steps(self) -> list[str]:
        """Return names of tools that have completed successfully.

        Returns:
            List of tool names with at least one successful execution.
        """
        return list(self._data["completed_steps"])

    # ------------------------------------------------------------------
    # Task results
    # ------------------------------------------------------------------

    def record_task_result(self, task_result: dict[str, Any]) -> None:
        """Record one user-task evaluation event in session state."""

        task_results = self._data.setdefault("task_results", [])
        if not isinstance(task_results, list):
            task_results = []
            self._data["task_results"] = task_results
        task_results.append(dict(task_result))
        self._touch()

    def get_task_results(self) -> list[dict[str, Any]]:
        """Return recorded user-task evaluation events."""

        task_results = self._data.get("task_results", [])
        if not isinstance(task_results, list):
            return []
        return list(task_results)

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Return a persisted UI preference value."""

        preferences = self._data.get("preferences", {})
        if not isinstance(preferences, dict):
            return default
        return preferences.get(key, default)

    def set_preference(self, key: str, value: Any) -> None:
        """Persist a UI preference value."""

        preferences = self._data.setdefault("preferences", {})
        if not isinstance(preferences, dict):
            preferences = {}
            self._data["preferences"] = preferences
        preferences[key] = value
        self._touch()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Write current state to disk as JSON."""
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, default=str)

    def reset(self) -> None:
        """Clear all state (conversation, results, progress) and save."""
        preferences = self._data.get("preferences", {})
        if not isinstance(preferences, dict):
            preferences = {}
        self._data = {
            "conversation": [],
            "tool_results": [],
            "task_results": [],
            "completed_steps": [],
            "preferences": preferences,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self.save()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        with open(self.state_path, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        self._data.update(loaded)

    def _load_preferences(self) -> None:
        try:
            with open(self.state_path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return

        preferences = loaded.get("preferences") if isinstance(loaded, dict) else None
        if isinstance(preferences, dict):
            self._data["preferences"] = dict(preferences)

    def _touch(self) -> None:
        self._data["updated_at"] = time.time()
        self.save()
