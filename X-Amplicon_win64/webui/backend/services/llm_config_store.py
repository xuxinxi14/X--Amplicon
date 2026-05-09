"""Safe local LLM configuration management for the Web UI."""

from __future__ import annotations

import os
from pathlib import Path

from agent.config import AgentConfig, KNOWN_MODELS
from webui.backend.config import get_project_root
from webui.backend.models.settings import LLMConfigStatus, LLMConfigUpdate, LLMModelOption
from webui.backend.services.agent_help_service import _provider_from_model

ENV_FILE = get_project_root() / ".env"
MANAGED_KEYS = ("LLM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_API_BASE", "OPENAI_API_BASE", "DEFAULT_MODEL")


def _env_path() -> Path:
    return ENV_FILE


def _read_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _quote_env_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _upsert_env(lines: list[str], updates: dict[str, str | None]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key, _, _ = line.partition("=")
        key = key.strip().lstrip("\ufeff")
        if key not in updates:
            output.append(line)
            continue
        seen.add(key)
        value = updates[key]
        if value is None:
            continue
        output.append(f"{key}={_quote_env_value(value)}")

    appended = False
    for key, value in updates.items():
        if key in seen or value is None:
            continue
        if not appended and output and output[-1].strip():
            output.append("")
        appended = True
        output.append(f"{key}={_quote_env_value(value)}")
    return output


def _write_env(updates: dict[str, str | None]) -> None:
    path = _env_path()
    lines = _upsert_env(_read_lines(path), updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def get_llm_config_status() -> LLMConfigStatus:
    """Return secret-free LLM settings for the browser."""

    config = AgentConfig()
    return LLMConfigStatus(
        model=config.model,
        api_base=config.api_base,
        api_base_configured=bool(config.api_base),
        api_key_configured=bool(config.api_key),
        provider=_provider_from_model(config.model),
        env_file_path=str(_env_path()),
        models=[LLMModelOption(value=value, label=label) for value, label in KNOWN_MODELS],
    )


def update_llm_config(payload: LLMConfigUpdate) -> LLMConfigStatus:
    """Persist local LLM settings to .env and current process environment."""

    updates: dict[str, str | None] = {}
    if payload.model is not None:
        model = payload.model.strip()
        if model:
            updates["DEFAULT_MODEL"] = model
            os.environ["DEFAULT_MODEL"] = model
    if payload.api_base is not None:
        api_base = payload.api_base.strip()
        updates["LLM_API_BASE"] = api_base or None
        if not api_base:
            updates["OPENAI_API_BASE"] = None
        if api_base:
            os.environ["LLM_API_BASE"] = api_base
        else:
            os.environ.pop("LLM_API_BASE", None)
            os.environ.pop("OPENAI_API_BASE", None)
    if payload.clear_api_key:
        updates["LLM_API_KEY"] = None
        updates["OPENAI_API_KEY"] = None
        updates["ANTHROPIC_API_KEY"] = None
        os.environ.pop("LLM_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)
    elif payload.api_key is not None:
        api_key = payload.api_key.strip()
        if api_key:
            updates["LLM_API_KEY"] = api_key
            os.environ["LLM_API_KEY"] = api_key

    if updates:
        _write_env(updates)
    return get_llm_config_status()
