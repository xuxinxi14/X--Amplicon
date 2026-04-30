"""Project and analysis setup API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import yaml

from webui.backend.config import resolve_path
from webui.backend.models.common import CommandSpec
from webui.backend.models.job import JobRecord
from webui.backend.models.project import (
    FastqPairingPreview,
    MetadataValidationResult,
    ParamsWriteResult,
    PipelineParamsDraft,
    ProjectCreate,
    ProjectRecord,
    ProjectUpdate,
)
from webui.backend.services import command_builder
from webui.backend.services.fastq_pairing import preview_fastq_pairs
from webui.backend.services.job_manager import manager
from webui.backend.services.metadata_validator import validate_metadata
from webui.backend.services.params_writer import write_pipeline_params
from webui.backend.services.project_store import (
    create_project,
    get_project,
    list_projects,
    update_project,
)
from webui.backend.services.result_indexer import final_dir_for_project
from webui.backend.services.settings_store import load_settings

router = APIRouter(prefix="/projects", tags=["projects"])


class MetadataValidationRequest(BaseModel):
    metadata_path: str | None = None
    sample_id_col: str = "SampleID"
    group_col: str = "Group"


class FastqPairingRequest(BaseModel):
    metadata_path: str | None = None
    seq_dir: str | None = None
    sample_id_col: str = "SampleID"
    read1_suffix: str = "_1.fq.gz"
    read2_suffix: str = "_2.fq.gz"


class VisualizationJobRequest(BaseModel):
    output_format: str = "html"
    metadata: str | None = None
    color_palette: str | None = None


class DifferentialJobRequest(BaseModel):
    comparisons: list[str] = []
    reference_group: str | None = None
    output_format: str = "html"
    group_col: str = "Group"
    sample_id_col: str = "SampleID"


def _project_or_404(project_id: str) -> ProjectRecord:
    try:
        return get_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _ensure_params(project: ProjectRecord) -> ProjectRecord:
    if project.params_path:
        return project
    result = write_pipeline_params(project)
    return update_project(project.id, {"params_path": result.params_path})


def _load_params_extras(project: ProjectRecord) -> dict[str, dict]:
    """Load optional Web UI sections from the generated params file."""

    if not project.params_path:
        return {}
    params_path = resolve_path(project.params_path, project.project_dir)
    if not params_path.is_file():
        return {}
    try:
        with params_path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
    except Exception:
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {
        "visualization": loaded.get("visualization") if isinstance(loaded.get("visualization"), dict) else {},
        "differential": loaded.get("differential") if isinstance(loaded.get("differential"), dict) else {},
    }


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _full_analysis_commands(project: ProjectRecord) -> list[tuple[str, CommandSpec]]:
    settings = load_settings()
    final_dir = final_dir_for_project(project)
    extras = _load_params_extras(project)
    visualization = extras.get("visualization", {})
    differential = extras.get("differential", {})
    metadata = str(resolve_path(project.metadata_path, project.project_dir)) if project.metadata_path else None
    output_format = str(visualization.get("output_format") or settings.default_plot_format or "html")

    commands: list[tuple[str, CommandSpec]] = [
        ("pipeline", command_builder.run_pipeline_config(project.params_path or "", settings)),
        (
            "visualization",
            command_builder.visualization_suite(
                str(final_dir),
                output_format=output_format,
                metadata=metadata,
                sample_id_col=project.sample_id_col,
                group_col=project.group_col,
                color_palette=_as_optional_string(visualization.get("color_palette")),
                settings=settings,
            ),
        ),
    ]

    comparisons = _as_string_list(differential.get("comparisons"))
    reference_group = _as_optional_string(differential.get("reference_group"))
    if metadata and (comparisons or reference_group):
        commands.append(
            (
                "differential",
                command_builder.differential_abundance(
                    otutab=str(final_dir / "otutab.txt"),
                    metadata=metadata,
                    output_dir=str(final_dir / "statistics" / "differential"),
                    taxonomy=str(final_dir / "taxonomy.tsv"),
                    comparisons=comparisons,
                    reference_group=reference_group,
                    output_format=str(differential.get("output_format") or settings.default_plot_format or "html"),
                    group_col=str(differential.get("group_col") or project.group_col),
                    sample_id_col=str(differential.get("sample_id_col") or project.sample_id_col),
                    settings=settings,
                ),
            )
        )

    commands.append(("report", command_builder.generate_report(str(final_dir), settings)))
    return commands


@router.get("", response_model=list[ProjectRecord])
def list_project_records() -> list[ProjectRecord]:
    return list_projects()


@router.post("", response_model=ProjectRecord)
def post_project(payload: ProjectCreate) -> ProjectRecord:
    try:
        return create_project(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}", response_model=ProjectRecord)
def get_project_record(project_id: str) -> ProjectRecord:
    return _project_or_404(project_id)


@router.put("/{project_id}", response_model=ProjectRecord)
def put_project(project_id: str, payload: ProjectUpdate) -> ProjectRecord:
    _project_or_404(project_id)
    try:
        return update_project(project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/validate-metadata", response_model=MetadataValidationResult)
def post_validate_metadata(project_id: str, payload: MetadataValidationRequest) -> MetadataValidationResult:
    project = _project_or_404(project_id)
    metadata_path = payload.metadata_path or project.metadata_path
    if not metadata_path:
        raise HTTPException(status_code=400, detail="metadata_path is required.")
    result = validate_metadata(
        metadata_path,
        sample_id_col=payload.sample_id_col or project.sample_id_col,
        group_col=payload.group_col or project.group_col,
        base_dir=project.project_dir,
    )
    update_project(
        project_id,
        {
            "metadata_path": metadata_path,
            "sample_id_col": payload.sample_id_col,
            "group_col": payload.group_col,
        },
    )
    return result


@router.post("/{project_id}/preview-pairs", response_model=FastqPairingPreview)
def post_preview_pairs(project_id: str, payload: FastqPairingRequest) -> FastqPairingPreview:
    project = _project_or_404(project_id)
    metadata_path = payload.metadata_path or project.metadata_path
    seq_dir = payload.seq_dir or project.seq_dir
    if not metadata_path or not seq_dir:
        raise HTTPException(status_code=400, detail="metadata_path and seq_dir are required.")
    result = preview_fastq_pairs(
        metadata_path,
        seq_dir,
        sample_id_col=payload.sample_id_col or project.sample_id_col,
        read1_suffix=payload.read1_suffix or project.read1_suffix,
        read2_suffix=payload.read2_suffix or project.read2_suffix,
        base_dir=project.project_dir,
    )
    update_project(
        project_id,
        {
            "metadata_path": metadata_path,
            "seq_dir": seq_dir,
            "sample_id_col": payload.sample_id_col,
            "read1_suffix": payload.read1_suffix,
            "read2_suffix": payload.read2_suffix,
        },
    )
    return result


@router.post("/{project_id}/write-params", response_model=ParamsWriteResult)
def post_write_params(project_id: str, payload: PipelineParamsDraft | None = None) -> ParamsWriteResult:
    project = _project_or_404(project_id)
    try:
        result = write_pipeline_params(project, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    update_project(project_id, {"params_path": result.params_path})
    return result


@router.post("/{project_id}/preflight", response_model=JobRecord)
def post_preflight(project_id: str) -> JobRecord:
    project = _ensure_params(_project_or_404(project_id))
    settings = load_settings()
    command = command_builder.check_pipeline_config(project.params_path or "", settings)
    record = manager.start_job(job_type="preflight", command=command, project_id=project_id, initial_status="checking")
    update_project(project_id, {"last_job_id": record.id})
    return record


@router.post("/{project_id}/run", response_model=JobRecord)
def post_run(project_id: str) -> JobRecord:
    project = _ensure_params(_project_or_404(project_id))
    commands = _full_analysis_commands(project)
    record = manager.start_sequence_job(
        job_type="full_analysis",
        commands=commands,
        project_id=project_id,
        initial_status="running",
    )
    update_project(project_id, {"last_job_id": record.id})
    return record


@router.post("/{project_id}/visualization", response_model=JobRecord)
def post_visualization(project_id: str, payload: VisualizationJobRequest) -> JobRecord:
    project = _project_or_404(project_id)
    settings = load_settings()
    metadata = payload.metadata or project.metadata_path
    resolved_metadata = str(resolve_path(metadata, project.project_dir)) if metadata else None
    command = command_builder.visualization_suite(
        str(final_dir_for_project(project)),
        output_format=payload.output_format,
        metadata=resolved_metadata,
        sample_id_col=project.sample_id_col,
        group_col=project.group_col,
        color_palette=payload.color_palette,
        settings=settings,
    )
    record = manager.start_job(job_type="visualization", command=command, project_id=project_id, initial_status="running")
    update_project(project_id, {"last_job_id": record.id})
    return record


@router.post("/{project_id}/differential", response_model=JobRecord)
def post_differential(project_id: str, payload: DifferentialJobRequest) -> JobRecord:
    project = _project_or_404(project_id)
    final_dir = final_dir_for_project(project)
    metadata_path = project.metadata_path
    if not metadata_path:
        raise HTTPException(status_code=400, detail="metadata_path is required for differential abundance.")
    resolved_metadata = str(resolve_path(metadata_path, project.project_dir))
    settings = load_settings()
    command = command_builder.differential_abundance(
        otutab=str(final_dir / "otutab.txt"),
        metadata=resolved_metadata,
        output_dir=str(final_dir / "statistics" / "differential"),
        taxonomy=str(final_dir / "taxonomy.tsv"),
        comparisons=payload.comparisons,
        reference_group=payload.reference_group,
        output_format=payload.output_format,
        group_col=payload.group_col,
        sample_id_col=payload.sample_id_col,
        settings=settings,
    )
    record = manager.start_job(job_type="differential", command=command, project_id=project_id, initial_status="running")
    update_project(project_id, {"last_job_id": record.id})
    return record


@router.post("/{project_id}/report", response_model=JobRecord)
def post_report(project_id: str) -> JobRecord:
    project = _project_or_404(project_id)
    settings = load_settings()
    command = command_builder.generate_report(str(final_dir_for_project(project)), settings)
    record = manager.start_job(job_type="report", command=command, project_id=project_id, initial_status="running")
    update_project(project_id, {"last_job_id": record.id})
    return record
