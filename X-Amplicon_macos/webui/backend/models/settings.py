"""Settings models for the Web UI backend."""

from __future__ import annotations

import os
from typing import Literal

from pydantic import Field

from webui.backend.models.common import WebUIBaseModel


def default_usearch_path() -> str:
    return r"bin\windows\usearch.exe" if os.name == "nt" else "bin/usearch"


def default_vsearch_path() -> str:
    return r"bin\windows\vsearch.exe" if os.name == "nt" else "bin/vsearch"


class WebUISettings(WebUIBaseModel):
    """Local Web UI settings persisted under .xamplicon_webui."""

    language: Literal["Chinese", "English"] = "Chinese"
    python_executable: str | None = None
    default_output_root: str = "work"
    default_metadata_path: str = "metadata.txt"
    default_seq_dir: str = "seq"
    default_group_col: str = "Group"
    default_sample_id_col: str = "SampleID"
    usearch_path: str = Field(default_factory=default_usearch_path)
    vsearch_path: str = Field(default_factory=default_vsearch_path)
    default_plot_format: Literal["html", "png", "pdf", "svg", "all"] = "html"
    authorized_dirs: list[str] = Field(default_factory=list)


class LLMModelOption(WebUIBaseModel):
    """One selectable LiteLLM model option for the Web UI."""

    value: str
    label: str


class LLMConfigStatus(WebUIBaseModel):
    """Secret-free LLM configuration status for settings UI."""

    model: str
    api_base: str = ""
    api_base_configured: bool = False
    api_key_configured: bool = False
    provider: str = "default"
    env_file_path: str
    models: list[LLMModelOption] = Field(default_factory=list)


class LLMConfigUpdate(WebUIBaseModel):
    """Payload for updating local LLM config. API key is never returned."""

    model: str | None = None
    api_base: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False
