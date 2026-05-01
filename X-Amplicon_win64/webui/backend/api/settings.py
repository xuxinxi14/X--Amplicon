"""Settings API routes."""

from __future__ import annotations

from fastapi import APIRouter

from webui.backend.models.settings import LLMConfigStatus, LLMConfigUpdate, WebUISettings
from webui.backend.services.llm_config_store import get_llm_config_status, update_llm_config
from webui.backend.services.settings_store import load_settings, save_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=WebUISettings)
def get_settings() -> WebUISettings:
    return load_settings()


@router.put("", response_model=WebUISettings)
def put_settings(settings: WebUISettings) -> WebUISettings:
    return save_settings(settings)


@router.get("/llm", response_model=LLMConfigStatus)
def get_llm_settings() -> LLMConfigStatus:
    return get_llm_config_status()


@router.put("/llm", response_model=LLMConfigStatus)
def put_llm_settings(payload: LLMConfigUpdate) -> LLMConfigStatus:
    return update_llm_config(payload)
