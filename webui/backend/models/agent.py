"""Agent and help API models for the Web UI backend."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from webui.backend.models.common import WebUIBaseModel


class AgentStatusResponse(WebUIBaseModel):
    """Safe, secret-free status for the optional LLM agent layer."""

    status: Literal["online", "offline", "no-key"]
    llm_available: bool
    key_configured: bool
    model: str
    api_base_configured: bool
    provider: str
    message: str
    capabilities: list[str] = Field(default_factory=list)
    disabled_reason: str | None = None


class AgentExplainRequest(WebUIBaseModel):
    """Payload for asking the help layer to explain an error or parameter choice."""

    question: str = ""
    technical_text: str = ""
    context_type: Literal[
        "general",
        "preflight",
        "metadata",
        "fastq",
        "database",
        "parameters",
        "results",
        "differential",
    ] = "general"
    project_summary: str = ""
    language: Literal["Chinese", "English"] = "Chinese"
    prefer_llm: bool = True


class AgentExplainResponse(WebUIBaseModel):
    """Structured explanation returned to the browser UI."""

    status: Literal["ok", "warning", "failed"] = "ok"
    mode: Literal["rule_based", "llm", "fallback"] = "rule_based"
    title: str
    summary: str
    likely_causes: list[str] = Field(default_factory=list)
    recovery_steps: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw_response: str | None = None
