"""Pipeline params writer for Web UI-created projects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from webui.backend.config import resolve_path
from webui.backend.models.project import ParamsWriteResult, PipelineParamsDraft, ProjectRecord

PIPELINE_PARAM_ORDER = (
    "metadata_path",
    "seq_dir",
    "output_root",
    "read1_suffix",
    "read2_suffix",
    "fastq_stripleft",
    "fastq_stripright",
    "fastq_maxee_rate",
    "feature_method",
    "feature_minsize",
    "feature_identity",
    "chimera_mode",
    "reference_db",
    "otutab_method",
    "otutab_identity",
    "annotation_database",
    "sintax_cutoff",
    "filter_route",
    "beta_tree_path",
    "rarefaction_depth",
    "rarefaction_seed",
    "threads",
    "usearch_path",
    "vsearch_path",
    "command_timeout",
)


def _draft_from_project(project: ProjectRecord, draft: PipelineParamsDraft | None) -> PipelineParamsDraft:
    raw = draft.model_dump(mode="json") if draft else PipelineParamsDraft().model_dump(mode="json")
    raw["metadata_path"] = raw.get("metadata_path") or project.metadata_path
    raw["seq_dir"] = raw.get("seq_dir") or project.seq_dir
    raw["output_root"] = raw.get("output_root") or project.output_root
    raw["read1_suffix"] = raw.get("read1_suffix") or project.read1_suffix
    raw["read2_suffix"] = raw.get("read2_suffix") or project.read2_suffix
    return PipelineParamsDraft(**raw)


def build_run_pipeline_params(project: ProjectRecord, draft: PipelineParamsDraft | None = None) -> dict[str, Any]:
    """Build the run_pipeline mapping used by process.py."""

    resolved_draft = _draft_from_project(project, draft)
    payload = resolved_draft.model_dump(mode="json")
    project_dir = resolve_path(project.project_dir)
    for path_key in ("metadata_path", "seq_dir", "output_root"):
        if payload.get(path_key):
            payload[path_key] = str(resolve_path(str(payload[path_key]), project_dir))
    run_pipeline: dict[str, Any] = {}
    for key in PIPELINE_PARAM_ORDER:
        value = payload.get(key)
        if value is None:
            continue
        run_pipeline[key] = value
    if not run_pipeline.get("metadata_path"):
        raise ValueError("metadata_path is required before writing pipeline params.")
    if not run_pipeline.get("seq_dir"):
        raise ValueError("seq_dir is required before writing pipeline params.")
    return run_pipeline


def write_pipeline_params(
    project: ProjectRecord,
    draft: PipelineParamsDraft | None = None,
    *,
    filename: str = "pipeline_params.webui.yaml",
) -> ParamsWriteResult:
    """Write a Web UI params YAML file without overwriting pipeline_params.yaml."""

    project_dir = resolve_path(project.project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    params_path = project_dir / filename
    resolved_draft = _draft_from_project(project, draft)
    draft_payload = resolved_draft.model_dump(mode="json")
    run_pipeline = build_run_pipeline_params(project, draft)
    payload = {
        "run_pipeline": run_pipeline,
        "visualization": {
            "color_palette": draft_payload.get("color_palette"),
        },
        "differential": draft_payload.get("differential") or {},
    }
    with params_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# X-Amplicon Web UI generated pipeline parameters.\n")
        handle.write("# This file is safe to regenerate from the Web UI.\n\n")
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)
    return ParamsWriteResult(
        status="passed",
        project_id=project.id,
        params_path=str(params_path),
        message="Pipeline params written successfully.",
        run_pipeline=run_pipeline,
    )
