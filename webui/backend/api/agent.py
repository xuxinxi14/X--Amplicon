"""Agent and help API routes."""

from __future__ import annotations

from fastapi import APIRouter

from webui.backend.models.agent import AgentExplainRequest, AgentExplainResponse, AgentStatusResponse
from webui.backend.services.agent_help_service import explain_agent_issue, get_agent_status

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/status")
def agent_status() -> AgentStatusResponse:
    """Return secret-free LLM/Agent status for the Web UI."""

    return get_agent_status()


@router.post("/explain")
def agent_explain(payload: AgentExplainRequest) -> AgentExplainResponse:
    """Explain an error, log excerpt, or parameter question."""

    return explain_agent_issue(payload)
