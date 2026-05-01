"""Project and analysis-setup models for the Web UI backend."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from webui.backend.models.common import WebUIBaseModel, utc_now_iso


class ProjectCreate(WebUIBaseModel):
    """Payload for creating a project record."""

    name: str
    project_dir: str | None = None
    output_root: str = "work"
    analysis_type: str = "16S rRNA"


class ProjectUpdate(WebUIBaseModel):
    """Partial project update payload."""

    name: str | None = None
    project_dir: str | None = None
    output_root: str | None = None
    analysis_type: str | None = None
    metadata_path: str | None = None
    seq_dir: str | None = None
    sample_id_col: str | None = None
    group_col: str | None = None
    read1_suffix: str | None = None
    read2_suffix: str | None = None
    params_path: str | None = None
    last_job_id: str | None = None


class ProjectRecord(WebUIBaseModel):
    """Persisted Web UI project record."""

    id: str
    name: str
    project_dir: str
    output_root: str = "work"
    analysis_type: str = "16S rRNA"
    metadata_path: str | None = None
    seq_dir: str | None = None
    sample_id_col: str = "SampleID"
    group_col: str = "Group"
    read1_suffix: str = "_1.fq.gz"
    read2_suffix: str = "_2.fq.gz"
    params_path: str | None = None
    last_job_id: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class GroupSummary(WebUIBaseModel):
    """Summary for one metadata group."""

    group: str
    count: int
    samples: list[str] = Field(default_factory=list)


class MetadataValidationResult(WebUIBaseModel):
    """Structured metadata validation result."""

    status: Literal["passed", "warning", "failed"]
    metadata_path: str
    exists: bool = False
    readable: bool = False
    rows: int = 0
    columns: int = 0
    column_names: list[str] = Field(default_factory=list)
    sample_id_col: str = "SampleID"
    group_col: str = "Group"
    sample_count: int = 0
    groups: list[GroupSummary] = Field(default_factory=list)
    missing_columns: list[str] = Field(default_factory=list)
    duplicate_sample_ids: list[str] = Field(default_factory=list)
    empty_sample_ids: int = 0
    empty_group_values: int = 0
    messages: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class FastqPairRecord(WebUIBaseModel):
    """FASTQ pair status for one sample."""

    sample_id: str
    read1_path: str
    read2_path: str
    read1_exists: bool
    read2_exists: bool
    status: Literal["ok", "missing_r1", "missing_r2", "missing_both"]


class FastqPairingPreview(WebUIBaseModel):
    """Structured FASTQ pairing preview."""

    status: Literal["passed", "warning", "failed"]
    metadata_path: str
    seq_dir: str
    read1_suffix: str
    read2_suffix: str
    sample_count: int = 0
    matched_pairs: int = 0
    missing_read1: list[str] = Field(default_factory=list)
    missing_read2: list[str] = Field(default_factory=list)
    extra_fastq_files: list[str] = Field(default_factory=list)
    pairs: list[FastqPairRecord] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class PipelineParamsDraft(WebUIBaseModel):
    """Web UI draft for process.py run_pipeline params."""

    metadata_path: str | None = None
    seq_dir: str | None = None
    output_root: str = "work"
    read1_suffix: str = "_1.fq.gz"
    read2_suffix: str = "_2.fq.gz"
    fastq_stripleft: int = 29
    fastq_stripright: int = 18
    fastq_maxee_rate: float = 0.01
    feature_method: Literal["usearch-asv", "usearch-otu", "vsearch-otu"] = "usearch-asv"
    feature_minsize: int = 10
    feature_identity: float = 1.0
    chimera_mode: Literal["ref", "none"] = "ref"
    reference_db: str = "database/rdp_16s_v18.fa"
    otutab_method: Literal["usearch", "vsearch"] = "usearch"
    otutab_identity: float = 1.0
    annotation_database: str = "rdp_16s_v18"
    sintax_cutoff: float = 0.1
    filter_route: Literal["16s", "its", "none"] = "16s"
    beta_tree_path: str | None = None
    rarefaction_depth: int = 8000
    rarefaction_seed: int = 1
    threads: int = 1
    usearch_path: str | None = r"bin\windows\usearch.exe"
    vsearch_path: str | None = r"bin\windows\vsearch.exe"
    command_timeout: float | None = None
    color_palette: str | None = None
    differential: dict[str, Any] = Field(default_factory=dict)


class ParamsWriteResult(WebUIBaseModel):
    """Result returned after writing a pipeline params file."""

    status: Literal["passed", "failed"]
    params_path: str
    project_id: str
    message: str
    run_pipeline: dict[str, Any] = Field(default_factory=dict)
