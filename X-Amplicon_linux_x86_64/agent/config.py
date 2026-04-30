"""Configuration loader for the X-Amplicon agent.

Reads settings from environment variables and an optional .env file.
Priority order (highest to lowest):
  1. Explicit constructor arguments
  2. Environment variables (already set before process start)
  3. .env file in the project root
  4. Built-in defaults

Supported variables:
  LLM_API_KEY      - API key sent to the LLM provider (generic)
  LLM_API_BASE     - Custom base URL for OpenAI-compatible proxy endpoints
  DEFAULT_MODEL    - Default model string passed to LiteLLM
  OPENAI_API_KEY   - Fallback if LLM_API_KEY is not set
  ANTHROPIC_API_KEY - Fallback if LLM_API_KEY is not set
"""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

DEFAULT_MODEL_FALLBACK = "claude-sonnet-4-6"
PLACEHOLDER_API_KEYS = {
    "sk-your-actual-key-here",
    "sk-...",
    "your-api-key",
    "your-actual-key",
    "replace-me",
    "changeme",
}

# Models listed here are shown by --list-models. Not exhaustive.
KNOWN_MODELS: list[tuple[str, str]] = [
    ("claude-sonnet-4-6",           "Anthropic - Claude Sonnet 4.6 (default)"),
    ("claude-opus-4-7",             "Anthropic - Claude Opus 4.7"),
    ("claude-haiku-4-5-20251001",   "Anthropic - Claude Haiku 4.5"),
    ("gpt-4o",                      "OpenAI - GPT-4o"),
    ("gpt-4o-mini",                 "OpenAI - GPT-4o Mini"),
    ("openai/gpt-4o",               "OpenAI via proxy - GPT-4o"),
    ("gemini/gemini-2.0-flash-exp", "Google - Gemini 2.0 Flash (experimental)"),
    ("gemini/gemini-1.5-pro",       "Google - Gemini 1.5 Pro"),
    ("openai/qwen-max",             "Alibaba Qwen Max (via OpenAI-compatible proxy)"),
    ("openai/qwen-plus",            "Alibaba Qwen Plus (via OpenAI-compatible proxy)"),
    ("openai/deepseek-chat",        "DeepSeek Chat (via OpenAI-compatible proxy)"),
    ("openai/deepseek-reasoner",    "DeepSeek Reasoner (via OpenAI-compatible proxy)"),
]


def _load_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict. Ignores comments and blank lines.

    Args:
        path: Path to the .env file.

    Returns:
        Dict of key-value pairs. Values are stripped of surrounding quotes.
    """
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    with open(path, encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip().lstrip("\ufeff")
            value = value.strip().strip('"').strip("'")
            if key:
                result[key] = value
    return result


def _get_env(key: str, env_file_values: dict[str, str], default: str = "") -> str:
    """Read a variable from os.environ first, then .env file, then default.

    Args:
        key: Environment variable name.
        env_file_values: Pre-parsed .env file contents.
        default: Value to return if the key is not found anywhere.

    Returns:
        The resolved string value.
    """
    return os.environ.get(key) or env_file_values.get(key) or default


def _clean_api_key(value: str) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if not text or lowered in PLACEHOLDER_API_KEYS:
        return ""
    if "your-" in lowered or "replace" in lowered:
        return ""
    return text


class AgentConfig:
    """Resolved configuration for the agent.

    Args:
        model: Override the model string. Falls back to DEFAULT_MODEL env var,
            then .env, then DEFAULT_MODEL_FALLBACK.
        api_key: Override the API key. Falls back to LLM_API_KEY, then
            OPENAI_API_KEY, then ANTHROPIC_API_KEY.
        api_base: Override the base URL. Falls back to LLM_API_BASE env var.
        env_file: Path to a .env file. Defaults to .env in the project root.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        env_file: str | Path | None = None,
    ) -> None:
        env_path = Path(env_file) if env_file else _ENV_FILE
        _env = _load_env_file(env_path)

        self.model: str = (
            model
            or _get_env("DEFAULT_MODEL", _env)
            or DEFAULT_MODEL_FALLBACK
        )

        self.api_key: str = _clean_api_key(
            api_key
            or _get_env("LLM_API_KEY", _env)
            or _get_env("OPENAI_API_KEY", _env)
            or _get_env("ANTHROPIC_API_KEY", _env)
        )

        self.api_base: str = (
            api_base
            or _get_env("LLM_API_BASE", _env)
            or _get_env("OPENAI_API_BASE", _env)
        )

    def validate(self) -> None:
        """Raise ValueError if the configuration is unusable.

        Raises:
            ValueError: If no API key is available.
        """
        if not self.api_key:
            raise ValueError(
                "No API key found. Set LLM_API_KEY in your .env file or as an "
                "environment variable.\n"
                "  Windows: set LLM_API_KEY=sk-...\n"
                "  Linux/macOS: export LLM_API_KEY=sk-...\n"
                "  Or create a .env file in the project root (see .env.example)."
            )

    def summary(self) -> str:
        """Return a human-readable one-liner for display at startup.

        Returns:
            String showing model and masked key/base info.
        """
        key_hint = f"{self.api_key[:8]}..." if self.api_key else "(not set)"
        base_hint = self.api_base or "(provider default)"
        return f"model={self.model}  key={key_hint}  base={base_hint}"
