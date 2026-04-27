"""Analysis report generator for completed X-Amplicon runs."""

from __future__ import annotations

import datetime as _dt
import html
import json
import math
import os
import re
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .viz_common import (
    DEFAULT_FINAL_DIR,
    ensure_output_dir,
    read_distance_matrix,
    read_table,
    write_text_file,
)

DEFAULT_REPORT_DIR = os.path.join(DEFAULT_FINAL_DIR, "report")
DEFAULT_REPORT_MD = "analysis_report.md"
DEFAULT_REPORT_HTML = "analysis_report.html"
DEFAULT_REPORT_DATA = "analysis_report_data.json"
SUMMARY_COLUMNS = {"all", "total", "sum", "overall"}


def _now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _load_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    resolved = os.path.abspath(path)
    if not os.path.isfile(resolved):
        return None
    with open(resolved, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else None


def _safe_table(path: str | None, label: str, index_col: int | str | None = None) -> pd.DataFrame | None:
    if not path or not os.path.isfile(os.path.abspath(path)):
        return None
    try:
        return read_table(path, label, index_col=index_col)
    except Exception:
        return None


def _get_nested(data: Mapping[str, Any] | None, *keys: str) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _first_existing(*paths: Any) -> str | None:
    for path in paths:
        if isinstance(path, str) and path.strip():
            resolved = os.path.abspath(path)
            if os.path.exists(resolved):
                return resolved
    return None


def _format_number(value: Any, digits: int = 3) -> str:
    if value is None:
        return "NA"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "NA"
    if abs(number) >= 1000:
        return f"{number:,.0f}"
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def _format_duration(seconds: Any) -> str:
    try:
        total = float(seconds)
    except (TypeError, ValueError):
        return "NA"
    if not math.isfinite(total):
        return "NA"
    if total < 60:
        return f"{total:.1f} s"
    minutes, sec = divmod(total, 60)
    if minutes < 60:
        return f"{int(minutes)} min {int(sec)} s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)} h {int(minutes)} min"


def _duration_from_timestamps(started_at: str | None, completed_at: str | None) -> float | None:
    if not started_at or not completed_at:
        return None
    try:
        start = _dt.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = _dt.datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (end - start).total_seconds()


def _rel_link(path: str, base_dir: str) -> str:
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(base_dir))
    except ValueError:
        rel = os.path.abspath(path)
    return rel.replace(os.sep, "/")


def _markdown_link(label: str, path: str | None, base_dir: str) -> str:
    if not path:
        return "NA"
    if not os.path.exists(os.path.abspath(path)):
        return f"`{path}`"
    return f"[{label}]({_rel_link(path, base_dir)})"


def _write_json(path: str, data: Mapping[str, Any]) -> str:
    resolved = os.path.abspath(path)
    parent = os.path.dirname(resolved)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(resolved, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, default=str)
        handle.write("\n")
    return resolved


def _resolve_paths(
    final_dir: str | None,
    summary_path: str | None,
    provenance_path: str | None,
    output_dir: str | None,
) -> dict[str, str | None]:
    resolved_summary = os.path.abspath(summary_path) if summary_path else None
    if resolved_summary and not os.path.isfile(resolved_summary):
        raise FileNotFoundError(f"run_summary.json not found: {resolved_summary}")

    resolved_final = os.path.abspath(final_dir or DEFAULT_FINAL_DIR)
    if resolved_summary:
        resolved_final = os.path.abspath(os.path.dirname(resolved_summary))
    if not os.path.isdir(resolved_final):
        raise FileNotFoundError(f"final_dir not found: {resolved_final}")

    resolved_summary = resolved_summary or _first_existing(os.path.join(resolved_final, "run_summary.json"))
    resolved_provenance = provenance_path
    if resolved_provenance is None:
        summary = _load_json(resolved_summary)
        resolved_provenance = (
            _get_nested(summary, "provenance", "json")
            or _get_nested(summary, "provenance_path")
            or os.path.join(resolved_final, "provenance.json")
        )
    resolved_provenance = _first_existing(resolved_provenance)
    resolved_output = ensure_output_dir(output_dir or os.path.join(resolved_final, "report"))
    return {
        "final_dir": resolved_final,
        "summary_path": resolved_summary,
        "provenance_path": resolved_provenance,
        "output_dir": resolved_output,
    }


def _metadata_summary(path: str | None) -> dict[str, Any]:
    table = _safe_table(path, "metadata")
    if table is None or table.empty:
        return {"path": path, "sample_count": None, "group_counts": {}}
    lower_map = {str(column).strip().lower(): column for column in table.columns}
    sample_col = lower_map.get("sampleid", table.columns[0])
    group_col = lower_map.get("group")
    result: dict[str, Any] = {
        "path": os.path.abspath(path) if path else None,
        "sample_count": int(table[sample_col].astype(str).str.strip().replace("", np.nan).dropna().nunique()),
        "group_column": str(group_col) if group_col is not None else None,
        "group_counts": {},
    }
    if group_col is not None:
        counts = table[group_col].astype(str).str.strip().value_counts().sort_index()
        result["group_counts"] = {str(key): int(value) for key, value in counts.items()}
    return result


def _feature_table_summary(path: str | None) -> dict[str, Any]:
    table = _safe_table(path, "feature table", index_col=0)
    if table is None or table.empty:
        return {"path": path, "available": False}
    values = table.apply(pd.to_numeric, errors="coerce").fillna(0.0)
    depths = values.sum(axis=0)
    prevalence = (values > 0).sum(axis=1)
    return {
        "path": os.path.abspath(path) if path else None,
        "available": True,
        "features": int(values.shape[0]),
        "samples": int(values.shape[1]),
        "total_count": float(values.to_numpy(dtype=float).sum()),
        "sample_depth_min": float(depths.min()) if len(depths) else 0.0,
        "sample_depth_median": float(depths.median()) if len(depths) else 0.0,
        "sample_depth_max": float(depths.max()) if len(depths) else 0.0,
        "mean_feature_prevalence": float(prevalence.mean()) if len(prevalence) else 0.0,
    }


def _alpha_summary(path: str | None, metadata: dict[str, Any]) -> dict[str, Any]:
    table = _safe_table(path, "alpha diversity")
    if table is None or table.empty:
        return {"path": path, "available": False, "metrics": {}}
    first_col = table.columns[0]
    lower_map = {str(column).strip().lower(): column for column in table.columns}
    sample_col = lower_map.get("sampleid", first_col)
    numeric_cols = [
        column for column in table.columns
        if column != sample_col and pd.api.types.is_numeric_dtype(pd.to_numeric(table[column], errors="coerce"))
    ]
    metrics: dict[str, dict[str, float]] = {}
    for column in numeric_cols:
        values = pd.to_numeric(table[column], errors="coerce").dropna()
        if values.empty:
            continue
        metrics[str(column)] = {
            "mean": float(values.mean()),
            "sd": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
            "min": float(values.min()),
            "max": float(values.max()),
        }
    return {
        "path": os.path.abspath(path) if path else None,
        "available": True,
        "sample_count": int(table[sample_col].astype(str).nunique()),
        "metrics": metrics,
    }


def _beta_summary(beta_matrices: Mapping[str, Any] | None, final_dir: str) -> dict[str, Any]:
    file_map: dict[str, str] = {}
    if isinstance(beta_matrices, Mapping):
        for metric, path in beta_matrices.items():
            if isinstance(path, str) and os.path.isfile(os.path.abspath(path)):
                file_map[str(metric)] = os.path.abspath(path)
    beta_dir = os.path.join(final_dir, "beta")
    if os.path.isdir(beta_dir):
        for name in os.listdir(beta_dir):
            root, suffix = os.path.splitext(name)
            if suffix.lower() in {".tsv", ".txt", ".csv"} and root not in file_map:
                file_map[root] = os.path.abspath(os.path.join(beta_dir, name))

    metrics: dict[str, dict[str, Any]] = {}
    for metric, path in sorted(file_map.items()):
        try:
            matrix = read_distance_matrix(path, metric)
        except Exception:
            continue
        values = matrix.to_numpy(dtype=float)
        if values.shape[0] < 2:
            upper = np.asarray([], dtype=float)
        else:
            upper = values[np.triu_indices_from(values, k=1)]
        metrics[metric] = {
            "path": path,
            "samples": int(matrix.shape[0]),
            "mean_pairwise": float(np.mean(upper)) if len(upper) else 0.0,
            "min_pairwise": float(np.min(upper)) if len(upper) else 0.0,
            "max_pairwise": float(np.max(upper)) if len(upper) else 0.0,
        }
    return {"available": bool(metrics), "metrics": metrics}


def _taxonomy_level_summary(path: str, top_n: int) -> list[dict[str, Any]]:
    table = _safe_table(path, "taxonomy summary")
    if table is None or table.empty:
        return []
    taxon_col = table.columns[0]
    sample_cols = [
        column for column in table.columns[1:]
        if str(column).strip().lower() not in SUMMARY_COLUMNS
    ]
    if not sample_cols:
        return []
    values = table.loc[:, sample_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    totals = values.sum(axis=0).replace(0, np.nan)
    relative = values.div(totals, axis=1).fillna(0.0) * 100.0
    mean_relative = relative.mean(axis=1)
    order = mean_relative.sort_values(ascending=False).head(int(top_n)).index
    rows: list[dict[str, Any]] = []
    for index in order:
        rows.append(
            {
                "taxon": str(table.loc[index, taxon_col]),
                "mean_relative_percent": float(mean_relative.loc[index]),
            }
        )
    return rows


def _taxonomy_summary(taxonomy_summaries: Mapping[str, Any] | None, final_dir: str, top_n: int) -> dict[str, Any]:
    file_map: dict[str, str] = {}
    if isinstance(taxonomy_summaries, Mapping):
        for level, path in taxonomy_summaries.items():
            if isinstance(path, str) and os.path.isfile(os.path.abspath(path)):
                file_map[str(level).title()] = os.path.abspath(path)
    taxonomy_dir = os.path.join(final_dir, "taxonomy_summary")
    if os.path.isdir(taxonomy_dir):
        for name in os.listdir(taxonomy_dir):
            root, suffix = os.path.splitext(name)
            if suffix.lower() in {".tsv", ".txt", ".csv"}:
                file_map.setdefault(root.title(), os.path.abspath(os.path.join(taxonomy_dir, name)))
    levels = {
        level: {
            "path": path,
            "top_taxa": _taxonomy_level_summary(path, top_n),
        }
        for level, path in sorted(file_map.items())
    }
    return {"available": bool(levels), "levels": levels}


def _differential_summary(final_dir: str) -> dict[str, Any]:
    root = os.path.join(final_dir, "statistics", "differential")
    result_root = os.path.join(root, "comparison_result")
    comparisons: list[dict[str, Any]] = []
    if not os.path.isdir(result_root):
        return {"available": False, "root": root, "comparisons": comparisons}

    for comparison in sorted(os.listdir(result_root)):
        comparison_dir = os.path.join(result_root, comparison)
        if not os.path.isdir(comparison_dir):
            continue
        result_path = os.path.join(comparison_dir, "differential_results.tsv")
        sig_path = os.path.join(comparison_dir, "differential_results_significant.tsv")
        result_table = _safe_table(result_path, "differential results")
        sig_table = _safe_table(sig_path, "significant differential results")
        level_counts: dict[str, int] = {}
        if result_table is not None and "level" in result_table.columns:
            counts = result_table["level"].astype(str).value_counts()
            level_counts = {str(key): int(value) for key, value in counts.items()}
        comparisons.append(
            {
                "comparison": comparison,
                "result_path": os.path.abspath(result_path) if os.path.isfile(result_path) else None,
                "significant_path": os.path.abspath(sig_path) if os.path.isfile(sig_path) else None,
                "tested_features": int(len(result_table)) if result_table is not None else None,
                "significant_features": int(len(sig_table)) if sig_table is not None else 0,
                "level_counts": level_counts,
                "volcano": _first_existing(os.path.join(root, "volcano_chart", comparison, "volcano.html")),
                "heatmap": _first_existing(os.path.join(root, "heatmap_chart", comparison, "heatmap.html")),
            }
        )
    return {"available": bool(comparisons), "root": root, "comparisons": comparisons}


def _find_key_figures(final_dir: str, differential: Mapping[str, Any]) -> list[dict[str, str]]:
    candidates = [
        ("Visualization index", os.path.join(final_dir, "plots", "index.html")),
        ("Alpha diversity boxplots", os.path.join(final_dir, "plots", "alpha_boxplot_chart", "alpha_boxplots.html")),
        ("Alpha rarefaction curve", os.path.join(final_dir, "plots", "alpha_rare_chart", "alpha_rarefaction_curve.html")),
        ("Beta PCoA", os.path.join(final_dir, "plots", "beta_pcoa_chart", "beta_pcoa_report.html")),
        ("Beta distance heatmaps", os.path.join(final_dir, "plots", "beta_heatmap_chart", "beta_heatmap_all_metrics.html")),
        ("Taxonomy stacked bars", os.path.join(final_dir, "plots", "taxonomy_stacked_bar_chart", "taxonomy_stacked_bar_report.html")),
        ("Taxonomy heatmaps", os.path.join(final_dir, "plots", "taxonomy_heatmap_chart", "taxonomy_heatmap_report.html")),
    ]
    for comparison in differential.get("comparisons", []) if isinstance(differential, Mapping) else []:
        if not isinstance(comparison, Mapping):
            continue
        label = str(comparison.get("comparison", "comparison"))
        candidates.append((f"Differential volcano: {label}", str(comparison.get("volcano") or "")))
        candidates.append((f"Differential heatmap: {label}", str(comparison.get("heatmap") or "")))

    figures: list[dict[str, str]] = []
    seen: set[str] = set()
    for label, path in candidates:
        if not path:
            continue
        resolved = os.path.abspath(path)
        if os.path.isfile(resolved) and resolved not in seen:
            seen.add(resolved)
            figures.append({"label": label, "path": resolved})
    return figures


def _table_lines(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def _build_report_data(
    final_dir: str,
    summary: dict[str, Any] | None,
    provenance: dict[str, Any] | None,
    summary_path: str | None,
    provenance_path: str | None,
    top_taxa: int,
) -> dict[str, Any]:
    outputs = summary.get("outputs", {}) if isinstance(summary, dict) else {}
    analysis_outputs = _get_nested(outputs, "analysis_outputs") or {}
    final_outputs = _get_nested(outputs, "final_outputs") or {}
    metadata_path = _first_existing(
        _get_nested(outputs, "metadata"),
        os.path.join(os.path.dirname(final_dir), "00_input", "metadata.txt"),
        os.path.join(os.getcwd(), "metadata.txt"),
    )
    feature_table = _first_existing(
        _get_nested(final_outputs, "feature_table"),
        os.path.join(final_dir, "otutab.txt"),
    )
    rarefied_table = _first_existing(
        _get_nested(analysis_outputs, "rarefied_otutab"),
        os.path.join(final_dir, "otutab_rare.txt"),
    )
    alpha_path = _first_existing(
        _get_nested(analysis_outputs, "alpha_diversity"),
        os.path.join(final_dir, "alpha", "alpha_diversity.tsv"),
    )
    metadata = _metadata_summary(metadata_path)
    differential = _differential_summary(final_dir)
    data = {
        "generated_at": _now_utc(),
        "final_dir": final_dir,
        "summary_path": summary_path,
        "provenance_path": provenance_path,
        "workflow": {
            "status": _get_nested(summary, "status") or _get_nested(provenance, "workflow", "status"),
            "started_at": _get_nested(summary, "started_at") or _get_nested(provenance, "workflow", "started_at"),
            "completed_at": _get_nested(summary, "completed_at") or _get_nested(provenance, "workflow", "completed_at"),
            "sample_count": len(_get_nested(summary, "sample_ids") or _get_nested(provenance, "workflow", "sample_ids") or []),
            "failed_step": _get_nested(summary, "failed_step") or _get_nested(provenance, "workflow", "failed_step"),
            "error": _get_nested(summary, "error") or _get_nested(provenance, "workflow", "error"),
        },
        "parameters": _get_nested(summary, "effective_params") or _get_nested(provenance, "effective_params") or {},
        "metadata": metadata,
        "feature_table": _feature_table_summary(feature_table),
        "rarefied_feature_table": _feature_table_summary(rarefied_table),
        "final_outputs": final_outputs if isinstance(final_outputs, Mapping) else {},
        "alpha": _alpha_summary(alpha_path, metadata),
        "beta": _beta_summary(_get_nested(analysis_outputs, "beta_matrices"), final_dir),
        "taxonomy": _taxonomy_summary(_get_nested(analysis_outputs, "taxonomy_summaries"), final_dir, top_taxa),
        "differential": differential,
        "provenance": provenance or {},
        "steps": summary.get("steps", []) if isinstance(summary, dict) else [],
    }
    data["figures"] = _find_key_figures(final_dir, differential)
    return data


def _append_overview(lines: list[str], data: Mapping[str, Any], report_dir: str) -> None:
    workflow = data.get("workflow", {})
    params = data.get("parameters", {})
    feature = data.get("feature_table", {})
    metadata = data.get("metadata", {})
    final_outputs = data.get("final_outputs", {})

    duration = _duration_from_timestamps(workflow.get("started_at"), workflow.get("completed_at")) if isinstance(workflow, Mapping) else None
    rows = [
        ("Run status", workflow.get("status", "unknown") if isinstance(workflow, Mapping) else "unknown"),
        ("Samples", metadata.get("sample_count") or workflow.get("sample_count") or "NA"),
        ("Metadata groups", ", ".join(f"{k}={v}" for k, v in (metadata.get("group_counts") or {}).items()) or "NA"),
        ("Feature method", params.get("feature_method", "NA") if isinstance(params, Mapping) else "NA"),
        ("OTU table method", params.get("otutab_method", "NA") if isinstance(params, Mapping) else "NA"),
        ("Annotation database", params.get("annotation_database", "NA") if isinstance(params, Mapping) else "NA"),
        ("Filter route", final_outputs.get("route") or params.get("filter_route", "NA") if isinstance(params, Mapping) else "NA"),
        ("Final features", final_outputs.get("kept_features") or feature.get("features") or "NA"),
        ("Rarefaction depth", params.get("rarefaction_depth", "NA") if isinstance(params, Mapping) else "NA"),
        ("Runtime", _format_duration(duration)),
    ]
    lines += ["## 1. Executive Summary", ""]
    lines.extend(_table_lines(["Item", "Value"], rows))
    lines += [
        "",
        "This report summarizes computational outputs generated by X-Amplicon. Biological interpretation, causal claims, and manuscript-level conclusions require researcher review of study design, metadata, covariates, and external evidence.",
        "",
    ]


def _append_workflow(lines: list[str], data: Mapping[str, Any]) -> None:
    lines += ["## 2. Workflow and Inputs", ""]
    steps = data.get("steps") or []
    if steps:
        rows = []
        for step in steps:
            if not isinstance(step, Mapping):
                continue
            duration = step.get("duration_seconds")
            if duration is None:
                duration = _duration_from_timestamps(step.get("started_at"), step.get("completed_at"))
            rows.append([
                step.get("name", "unknown"),
                step.get("status", "unknown"),
                _format_duration(duration),
                step.get("description", ""),
            ])
        lines.extend(_table_lines(["Step", "Status", "Duration", "Description"], rows))
    else:
        lines.append("_No step-level run summary was available._")
    lines += ["", "### Key Input and Output Files", ""]
    rows = []
    for label, key in (
        ("Run summary", "summary_path"),
        ("Provenance JSON", "provenance_path"),
        ("Final directory", "final_dir"),
    ):
        path = data.get(key)
        rows.append([label, path or "NA"])
    feature = data.get("feature_table", {})
    rarefied = data.get("rarefied_feature_table", {})
    if isinstance(feature, Mapping):
        rows.append(["Final feature table", feature.get("path") or "NA"])
    if isinstance(rarefied, Mapping):
        rows.append(["Rarefied feature table", rarefied.get("path") or "NA"])
    lines.extend(_table_lines(["Artifact", "Path"], rows))
    lines.append("")


def _append_feature_alpha_beta(lines: list[str], data: Mapping[str, Any]) -> None:
    lines += ["## 3. Community Summary", ""]
    feature = data.get("feature_table", {})
    rarefied = data.get("rarefied_feature_table", {})
    rows = []
    for label, summary in (("Final table", feature), ("Rarefied table", rarefied)):
        if isinstance(summary, Mapping) and summary.get("available"):
            rows.append([
                label,
                summary.get("features"),
                summary.get("samples"),
                _format_number(summary.get("total_count")),
                _format_number(summary.get("sample_depth_min")),
                _format_number(summary.get("sample_depth_median")),
                _format_number(summary.get("sample_depth_max")),
            ])
    if rows:
        lines.extend(_table_lines(["Table", "Features", "Samples", "Total count", "Min depth", "Median depth", "Max depth"], rows))
    else:
        lines.append("_No feature table summary was available._")
    lines += ["", "### Alpha Diversity", ""]
    alpha = data.get("alpha", {})
    metrics = alpha.get("metrics") if isinstance(alpha, Mapping) else {}
    if metrics:
        rows = [
            [metric, _format_number(stats.get("mean")), _format_number(stats.get("sd")), _format_number(stats.get("min")), _format_number(stats.get("max"))]
            for metric, stats in metrics.items()
            if isinstance(stats, Mapping)
        ]
        lines.extend(_table_lines(["Metric", "Mean", "SD", "Min", "Max"], rows))
    else:
        lines.append("_Alpha diversity results were not available._")
    lines += ["", "### Beta Diversity", ""]
    beta = data.get("beta", {})
    beta_metrics = beta.get("metrics") if isinstance(beta, Mapping) else {}
    if beta_metrics:
        rows = [
            [
                metric,
                stats.get("samples"),
                _format_number(stats.get("mean_pairwise")),
                _format_number(stats.get("min_pairwise")),
                _format_number(stats.get("max_pairwise")),
            ]
            for metric, stats in beta_metrics.items()
            if isinstance(stats, Mapping)
        ]
        lines.extend(_table_lines(["Metric", "Samples", "Mean pairwise", "Min pairwise", "Max pairwise"], rows))
    else:
        lines.append("_Beta diversity distance matrices were not available._")
    lines.append("")


def _append_taxonomy(lines: list[str], data: Mapping[str, Any]) -> None:
    lines += ["## 4. Taxonomic Composition", ""]
    taxonomy = data.get("taxonomy", {})
    levels = taxonomy.get("levels") if isinstance(taxonomy, Mapping) else {}
    if not levels:
        lines += ["_Taxonomy summary tables were not available._", ""]
        return
    preferred = [level for level in ("Phylum", "Genus", "Family", "Class", "Order", "Kingdom", "Species") if level in levels]
    for level in preferred[:3]:
        info = levels[level]
        top_taxa = info.get("top_taxa", []) if isinstance(info, Mapping) else []
        if not top_taxa:
            continue
        lines += [f"### Top {level} Taxa", ""]
        rows = [
            [item.get("taxon", "NA"), _format_number(item.get("mean_relative_percent"))]
            for item in top_taxa
            if isinstance(item, Mapping)
        ]
        lines.extend(_table_lines([level, "Mean relative abundance (%)"], rows))
        lines.append("")


def _append_differential_and_figures(lines: list[str], data: Mapping[str, Any], report_dir: str) -> None:
    lines += ["## 5. Statistical and Differential Outputs", ""]
    differential = data.get("differential", {})
    comparisons = differential.get("comparisons") if isinstance(differential, Mapping) else []
    if comparisons:
        rows = []
        for item in comparisons:
            if not isinstance(item, Mapping):
                continue
            rows.append([
                item.get("comparison", "NA"),
                item.get("tested_features", "NA"),
                item.get("significant_features", 0),
                ", ".join(f"{k}={v}" for k, v in (item.get("level_counts") or {}).items()) or "NA",
            ])
        lines.extend(_table_lines(["Comparison", "Tested features", "Significant features", "Level counts"], rows))
    else:
        lines.append("_Differential abundance statistics were not available._")
    lines += ["", "## 6. Key Figures", ""]
    figures = data.get("figures") or []
    if figures:
        for figure in figures:
            if not isinstance(figure, Mapping):
                continue
            label = str(figure.get("label", "Figure"))
            path = str(figure.get("path", ""))
            lines.append(f"- {_markdown_link(label, path, report_dir)}")
    else:
        lines.append("_No visualization files were found. Run `python process.py visualization-suite --final-dir work\\06_final` to generate plots._")
    lines.append("")


def _append_reproducibility(lines: list[str], data: Mapping[str, Any]) -> None:
    lines += ["## 7. Reproducibility Record", ""]
    provenance = data.get("provenance", {})
    project = provenance.get("project", {}) if isinstance(provenance, Mapping) else {}
    runtime = provenance.get("runtime", {}) if isinstance(provenance, Mapping) else {}
    tools = provenance.get("tools", {}) if isinstance(provenance, Mapping) else {}
    databases = provenance.get("databases", {}) if isinstance(provenance, Mapping) else {}
    rows = [
        ["Git commit", project.get("commit", "NA") if isinstance(project, Mapping) else "NA"],
        ["Git branch", project.get("branch", "NA") if isinstance(project, Mapping) else "NA"],
        ["Git dirty state", project.get("dirty", "NA") if isinstance(project, Mapping) else "NA"],
        ["Python", runtime.get("python_version", "NA") if isinstance(runtime, Mapping) else "NA"],
    ]
    for name, info in tools.items() if isinstance(tools, Mapping) else []:
        if isinstance(info, Mapping):
            rows.append([str(name), info.get("version") or info.get("path") or "NA"])
    for name, info in databases.items() if isinstance(databases, Mapping) else []:
        if isinstance(info, Mapping):
            rows.append([f"Database: {name}", info.get("sha256") or info.get("path") or "NA"])
    lines.extend(_table_lines(["Item", "Value"], rows))
    lines += [
        "",
        "## 8. Interpretation Boundary",
        "",
        "- The tables and figures above are computational summaries produced from the supplied input data and parameters.",
        "- X-Amplicon does not infer biological causality or validate experimental design.",
        "- Researchers should verify metadata grouping, sequencing depth, rarefaction decisions, statistical thresholds, potential confounders, and database suitability before drawing biological conclusions.",
        "- Differential abundance results should be interpreted with multiple-testing correction, sample size, and study-specific covariates in mind.",
        "",
    ]


def _build_markdown(data: Mapping[str, Any], report_dir: str) -> str:
    lines: list[str] = [
        "# X-Amplicon Analysis Report",
        "",
        f"_Generated: {data.get('generated_at', _now_utc())}_",
        "",
    ]
    _append_overview(lines, data, report_dir)
    _append_workflow(lines, data)
    _append_feature_alpha_beta(lines, data)
    _append_taxonomy(lines, data)
    _append_differential_and_figures(lines, data, report_dir)
    _append_reproducibility(lines, data)
    return "\n".join(lines).rstrip() + "\n"


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def _markdown_to_html(markdown: str) -> str:
    html_lines: list[str] = []
    in_list = False
    in_code = False
    lines = markdown.splitlines()
    index = 0

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            html_lines.append("</ul>")
            in_list = False

    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            close_list()
            if not in_code:
                html_lines.append("<pre><code>")
                in_code = True
            else:
                html_lines.append("</code></pre>")
                in_code = False
            index += 1
            continue
        if in_code:
            html_lines.append(html.escape(line))
            index += 1
            continue
        if not line.strip():
            close_list()
            index += 1
            continue
        if line.startswith("| ") and index + 1 < len(lines) and lines[index + 1].startswith("| "):
            close_list()
            table_rows: list[list[str]] = []
            while index < len(lines) and lines[index].startswith("| "):
                cells = [cell.strip() for cell in lines[index].strip("|").split("|")]
                if not all(set(cell) <= {"-", ":", " "} for cell in cells):
                    table_rows.append(cells)
                index += 1
            if table_rows:
                headers = table_rows[0]
                body = table_rows[1:]
                html_lines.append("<table><thead><tr>")
                html_lines.extend(f"<th>{_inline_markdown(cell)}</th>" for cell in headers)
                html_lines.append("</tr></thead><tbody>")
                for row in body:
                    html_lines.append("<tr>")
                    html_lines.extend(f"<td>{_inline_markdown(cell)}</td>" for cell in row)
                    html_lines.append("</tr>")
                html_lines.append("</tbody></table>")
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            close_list()
            level = len(heading.group(1))
            html_lines.append(f"<h{level}>{_inline_markdown(heading.group(2))}</h{level}>")
        elif line.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{_inline_markdown(line[2:])}</li>")
        else:
            close_list()
            html_lines.append(f"<p>{_inline_markdown(line)}</p>")
        index += 1
    close_list()
    if in_code:
        html_lines.append("</code></pre>")
    return "\n".join(html_lines)


def _build_html(markdown: str, data: Mapping[str, Any], report_dir: str) -> str:
    figures = [
        figure for figure in data.get("figures", [])
        if isinstance(figure, Mapping) and str(figure.get("path", "")).lower().endswith(".html")
    ][:8]
    figure_blocks: list[str] = []
    for figure in figures:
        label = html.escape(str(figure.get("label", "Figure")))
        path = _rel_link(str(figure.get("path")), report_dir)
        figure_blocks.append(
            f'<section class="figure-panel"><h3>{label}</h3>'
            f'<iframe src="{html.escape(path)}" loading="lazy"></iframe></section>'
        )
    figure_html = ""
    if figure_blocks:
        figure_html = (
            '<section class="embedded-figures"><h2>Embedded Interactive Figures</h2>'
            + "".join(figure_blocks)
            + "</section>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>X-Amplicon Analysis Report</title>
  <style>
    body {{
      margin: 0;
      padding: 28px 34px 42px;
      font-family: Arial, Helvetica, sans-serif;
      color: #202733;
      background: #ffffff;
      line-height: 1.55;
    }}
    main {{ max-width: 1180px; margin: 0 auto; }}
    h1 {{ font-size: 30px; margin: 0 0 18px; }}
    h2 {{ margin-top: 30px; padding-top: 14px; border-top: 1px solid #E5E7EB; }}
    h3 {{ margin-top: 20px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 12px 0 18px; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid #E5E7EB; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #F6F7F9; font-weight: 650; }}
    code {{ background: #F3F4F6; padding: 1px 4px; border-radius: 4px; }}
    pre {{ background: #F6F7F9; padding: 12px; overflow-x: auto; }}
    a {{ color: #2F6B9A; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .embedded-figures {{ margin-top: 34px; }}
    .figure-panel {{ margin: 18px 0 28px; }}
    .figure-panel iframe {{
      width: 100%;
      min-height: 680px;
      border: 1px solid #D8DEE6;
      border-radius: 6px;
      background: #ffffff;
    }}
  </style>
</head>
<body>
<main>
{_markdown_to_html(markdown)}
{figure_html}
</main>
</body>
</html>
"""


def generate_analysis_report(
    final_dir: str = DEFAULT_FINAL_DIR,
    summary_path: str | None = None,
    provenance_path: str | None = None,
    output_dir: str | None = None,
    include_html: bool = True,
    include_figures: bool = True,
    top_taxa: int = 10,
) -> dict[str, Any]:
    """Generate Markdown and HTML reports for a completed X-Amplicon run."""

    paths = _resolve_paths(final_dir, summary_path, provenance_path, output_dir)
    summary = _load_json(paths["summary_path"])
    provenance = _load_json(paths["provenance_path"])
    report_dir = str(paths["output_dir"])
    data = _build_report_data(
        final_dir=str(paths["final_dir"]),
        summary=summary,
        provenance=provenance,
        summary_path=paths["summary_path"],
        provenance_path=paths["provenance_path"],
        top_taxa=int(top_taxa),
    )
    if not include_figures:
        data["figures"] = []

    markdown = _build_markdown(data, report_dir)
    markdown_path = write_text_file(os.path.join(report_dir, DEFAULT_REPORT_MD), markdown)
    data_path = _write_json(os.path.join(report_dir, DEFAULT_REPORT_DATA), data)
    html_path: str | None = None
    if include_html:
        html_path = write_text_file(
            os.path.join(report_dir, DEFAULT_REPORT_HTML),
            _build_html(markdown, data, report_dir),
        )

    generated = [markdown_path, data_path]
    if html_path is not None:
        generated.append(html_path)
    return {
        "status": "success",
        "final_dir": paths["final_dir"],
        "summary_path": paths["summary_path"],
        "provenance_path": paths["provenance_path"],
        "output_dir": report_dir,
        "markdown": markdown_path,
        "html": html_path,
        "data": data_path,
        "generated_files": generated,
        "figures": data.get("figures", []),
    }


TOOL_DEFINITIONS = [
    {
        "name": "generate_analysis_report",
        "description": (
            "Generate a standard X-Amplicon analysis report from work/06_final. "
            "Writes Markdown, HTML, and a machine-readable report data JSON under "
            "work/06_final/report by default."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "final_dir": {"type": "string", "default": DEFAULT_FINAL_DIR},
                "summary_path": {"type": "string"},
                "provenance_path": {"type": "string"},
                "output_dir": {"type": "string", "default": DEFAULT_REPORT_DIR},
                "include_html": {"type": "boolean", "default": True},
                "include_figures": {"type": "boolean", "default": True},
                "top_taxa": {"type": "integer", "default": 10},
            },
        },
        "fn": generate_analysis_report,
    }
]
