"""Settings model for the local Web UI."""

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

    language: Literal["zh", "en"] = "zh"
    default_output_root: str = "work"
    default_metadata_path: str = "metadata.txt"
    default_seq_dir: str = "seq"
    default_group_col: str = "Group"
    default_sample_id_col: str = "SampleID"
    usearch_path: str = Field(default_factory=default_usearch_path)
    vsearch_path: str = Field(default_factory=default_vsearch_path)
    default_plot_format: Literal["html", "png", "pdf", "svg", "all"] = "all"
    authorized_dirs: list[str] = Field(default_factory=list)


class SettingsUpdate(WebUIBaseModel):
    language: Literal["zh", "en"] | None = None
    default_output_root: str | None = None
    default_metadata_path: str | None = None
    default_seq_dir: str | None = None
    default_group_col: str | None = None
    default_sample_id_col: str | None = None
    usearch_path: str | None = None
    vsearch_path: str | None = None
    default_plot_format: Literal["html", "png", "pdf", "svg", "all"] | None = None
    authorized_dirs: list[str] | None = None
