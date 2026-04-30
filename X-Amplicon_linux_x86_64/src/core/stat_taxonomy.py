"""Taxonomy/feature differential abundance statistics for X-Amplicon."""

from __future__ import annotations

import itertools
import math
import os
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from scipy import stats

from .viz_common import (
    DEFAULT_FINAL_DIR,
    apply_publication_theme,
    ensure_output_dir,
    read_table,
    sanitize_id,
    validate_output_format,
    write_html_figure,
    write_optional_static,
    write_table,
)

DEFAULT_DIFFERENTIAL_OUTPUT_DIR = os.path.join(DEFAULT_FINAL_DIR, "statistics", "differential")
DEFAULT_COMPARISON_RESULT_DIR = os.path.join(DEFAULT_DIFFERENTIAL_OUTPUT_DIR, "comparison_result")
DEFAULT_DIFFERENTIAL_VOLCANO_DIR = os.path.join(DEFAULT_DIFFERENTIAL_OUTPUT_DIR, "volcano_chart")
DEFAULT_DIFFERENTIAL_HEATMAP_DIR = os.path.join(DEFAULT_DIFFERENTIAL_OUTPUT_DIR, "heatmap_chart")
VALID_DIFFERENTIAL_METHODS = {"wilcox", "mannwhitney", "mannwhitneyu", "t.test", "ttest"}
INCLUDE_TRUE_VALUES = {"1", "true", "t", "yes", "y", "run", "include"}
TAXONOMY_COLUMNS = ("Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species")


def _resolve_sample_column(table: pd.DataFrame, sample_id_col: str) -> str:
    lower_map = {str(column).strip().lower(): column for column in table.columns}
    return lower_map.get(str(sample_id_col).strip().lower(), table.columns[0])


def _resolve_column(table: pd.DataFrame, requested: str, label: str) -> str:
    lower_map = {str(column).strip().lower(): column for column in table.columns}
    column = lower_map.get(str(requested).strip().lower())
    if column is None:
        raise ValueError(f"{label} column '{requested}' is missing.")
    return column


def _read_group_metadata(
    metadata_path: str,
    sample_id_col: str = "SampleID",
    group_col: str = "Group",
) -> pd.DataFrame:
    table = read_table(metadata_path, "metadata")
    sample_column = _resolve_sample_column(table, sample_id_col)
    group_column = _resolve_column(table, group_col, "metadata group")
    metadata = table.loc[:, [sample_column, group_column]].copy()
    metadata = metadata.rename(columns={sample_column: "SampleID", group_column: "Group"})
    metadata["SampleID"] = metadata["SampleID"].astype(str).str.strip()
    metadata["Group"] = metadata["Group"].astype(str).str.strip()
    metadata = metadata.loc[(metadata["SampleID"] != "") & (metadata["Group"] != "")].copy()

    if metadata.empty:
        raise ValueError("metadata has no valid SampleID/group rows.")

    conflicts = metadata.groupby("SampleID")["Group"].nunique()
    conflicts = conflicts.loc[conflicts > 1]
    if not conflicts.empty:
        raise ValueError(
            "metadata contains conflicting group labels for samples: "
            f"{conflicts.index.tolist()[:8]}"
        )

    metadata = metadata.drop_duplicates(subset=["SampleID"], keep="first")
    metadata = metadata.set_index("SampleID", drop=False)
    return metadata


def _read_otutab(otutab_path: str) -> pd.DataFrame:
    table = read_table(otutab_path, "OTU table", index_col=0)
    table.index = table.index.astype(str).str.strip()
    table.columns = [str(column).strip() for column in table.columns]
    if table.index.has_duplicates:
        raise ValueError("OTU table contains duplicate feature IDs.")
    if table.columns.has_duplicates:
        raise ValueError("OTU table contains duplicate sample IDs.")

    counts = table.apply(pd.to_numeric, errors="coerce")
    if counts.isna().to_numpy().any():
        raise ValueError("OTU table contains non-numeric or missing abundance values.")
    if (counts < 0).to_numpy().any():
        raise ValueError("OTU table contains negative abundance values.")
    return counts


def _read_taxonomy(taxonomy_path: str | None) -> pd.DataFrame | None:
    if not taxonomy_path:
        return None
    if not os.path.isfile(os.path.abspath(taxonomy_path)):
        return None

    taxonomy = read_table(taxonomy_path, "taxonomy")
    if "OTUID" in taxonomy.columns:
        taxonomy = taxonomy.set_index("OTUID", drop=False)
    else:
        taxonomy = taxonomy.copy()
        taxonomy.index = taxonomy.index.astype(str)
        taxonomy.insert(0, "OTUID", taxonomy.index)
    taxonomy.index = taxonomy.index.astype(str)
    taxonomy.index.name = None

    available_columns = ["OTUID", *[column for column in TAXONOMY_COLUMNS if column in taxonomy.columns]]
    return taxonomy.loc[:, available_columns].copy()


def _normalize_method(method: str) -> str:
    normalized = str(method).strip().lower()
    if normalized == "edgeR".lower():
        raise ValueError(
            "edgeR is not implemented in the Python differential module. "
            "Use method='wilcox' for the current distributed workflow."
        )
    if normalized not in VALID_DIFFERENTIAL_METHODS:
        raise ValueError(
            "method must be one of: wilcox, t.test. "
            "edgeR remains a planned optional R/Bioconductor extension."
        )
    return "t.test" if normalized in {"t.test", "ttest"} else "wilcox"


def _comparison_label(case_group: str, control_group: str) -> str:
    return f"{case_group}_vs_{control_group}"


def _parse_comparison_item(item: Any) -> tuple[str, str]:
    if isinstance(item, dict):
        case = item.get("case") or item.get("case_group") or item.get("treatment")
        control = item.get("control") or item.get("control_group") or item.get("reference")
        if case is None or control is None:
            raise ValueError(f"Comparison dict must contain case/control groups: {item}")
        return str(case).strip(), str(control).strip()

    if isinstance(item, (list, tuple)) and len(item) == 2:
        return str(item[0]).strip(), str(item[1]).strip()

    text = str(item).strip()
    for delimiter in ("_vs_", "-vs-", " vs ", ":", "|", ","):
        if delimiter in text:
            parts = [part.strip() for part in text.split(delimiter)]
            if len(parts) == 2 and all(parts):
                return parts[0], parts[1]
    if text.count("-") == 1:
        parts = [part.strip() for part in text.split("-")]
        if all(parts):
            return parts[0], parts[1]

    raise ValueError(
        f"Could not parse comparison '{item}'. Use CASE:CONTROL or CASE_vs_CONTROL."
    )


def _parse_comparisons(comparisons: Sequence[Any] | str | None) -> list[tuple[str, str]]:
    if comparisons is None:
        return []
    if isinstance(comparisons, str):
        raw_items = [
            item.strip()
            for item in comparisons.replace(";", "\n").splitlines()
            if item.strip()
        ]
    else:
        raw_items = list(comparisons)

    parsed: list[tuple[str, str]] = []
    for item in raw_items:
        case_group, control_group = _parse_comparison_item(item)
        if not case_group or not control_group:
            raise ValueError(f"Comparison contains an empty group: {item}")
        parsed.append((case_group, control_group))
    return list(dict.fromkeys(parsed))


def _group_counts(metadata: pd.DataFrame) -> dict[str, int]:
    return metadata["Group"].value_counts(sort=False).astype(int).to_dict()


def _comparison_rows(
    metadata: pd.DataFrame,
    comparisons: Sequence[tuple[str, str]],
    *,
    source: str,
    include: bool,
    min_samples_per_group: int,
) -> list[dict[str, Any]]:
    counts = _group_counts(metadata)
    rows: list[dict[str, Any]] = []
    for case_group, control_group in comparisons:
        case_n = int(counts.get(case_group, 0))
        control_n = int(counts.get(control_group, 0))
        issues: list[str] = []
        if case_group == control_group:
            issues.append("case and control groups are identical")
        if case_n == 0:
            issues.append(f"case group '{case_group}' is absent")
        if control_n == 0:
            issues.append(f"control group '{control_group}' is absent")
        if case_n and case_n < int(min_samples_per_group):
            issues.append(f"case group has n={case_n}, below min_samples_per_group")
        if control_n and control_n < int(min_samples_per_group):
            issues.append(f"control group has n={control_n}, below min_samples_per_group")

        rows.append(
            {
                "Comparison": _comparison_label(case_group, control_group),
                "CaseGroup": case_group,
                "ControlGroup": control_group,
                "CaseN": case_n,
                "ControlN": control_n,
                "Include": "yes" if include and not issues else "no",
                "Status": "ready" if not issues else "invalid",
                "Source": source,
                "Reason": "; ".join(issues),
            }
        )
    return rows


def build_differential_comparison_plan(
    metadata_path: str,
    output_dir: str = DEFAULT_DIFFERENTIAL_OUTPUT_DIR,
    group_col: str = "Group",
    sample_id_col: str = "SampleID",
    comparisons: Sequence[Any] | str | None = None,
    reference_group: str | None = None,
    min_samples_per_group: int = 2,
) -> dict[str, Any]:
    """Build a validated comparison plan from metadata.

    Explicit comparisons use CASE:CONTROL direction and are marked as included.
    When only a reference group is supplied, each non-reference group is compared
    against that reference. Without either, all pairwise candidates are written
    with Include=no so the user can confirm them before running.
    """

    metadata = _read_group_metadata(
        metadata_path,
        sample_id_col=sample_id_col,
        group_col=group_col,
    )
    groups = list(dict.fromkeys(metadata["Group"].astype(str).tolist()))
    if len(groups) < 2:
        raise ValueError("metadata must contain at least two groups for differential analysis.")

    parsed_comparisons = _parse_comparisons(comparisons)
    if parsed_comparisons:
        rows = _comparison_rows(
            metadata,
            parsed_comparisons,
            source="explicit",
            include=True,
            min_samples_per_group=min_samples_per_group,
        )
        mode = "explicit"
    elif reference_group:
        reference = str(reference_group).strip()
        if reference not in groups:
            raise ValueError(f"reference_group '{reference}' is not present in metadata groups: {groups}")
        reference_comparisons = [(group, reference) for group in groups if group != reference]
        rows = _comparison_rows(
            metadata,
            reference_comparisons,
            source="reference_group",
            include=True,
            min_samples_per_group=min_samples_per_group,
        )
        mode = "reference_group"
    else:
        candidate_comparisons = list(itertools.combinations(groups, 2))
        rows = _comparison_rows(
            metadata,
            candidate_comparisons,
            source="candidate_plan",
            include=False,
            min_samples_per_group=min_samples_per_group,
        )
        mode = "plan_required"

    plan = pd.DataFrame.from_records(
        rows,
        columns=[
            "Comparison",
            "CaseGroup",
            "ControlGroup",
            "CaseN",
            "ControlN",
            "Include",
            "Status",
            "Source",
            "Reason",
        ],
    )
    resolved_output_dir = ensure_output_dir(output_dir)
    plan_path = write_table(
        plan,
        os.path.join(resolved_output_dir, "comparison_plan.tsv"),
        include_index=False,
    )
    return {
        "status": mode,
        "metadata": os.path.abspath(metadata_path),
        "group_col": group_col,
        "groups": groups,
        "group_counts": _group_counts(metadata),
        "comparison_plan": plan_path,
        "plan": plan.to_dict(orient="records"),
    }


def _load_confirmed_plan(
    comparison_plan_path: str,
    min_samples_per_group: int,
) -> list[tuple[str, str]]:
    plan = read_table(comparison_plan_path, "comparison_plan")
    required = {"CaseGroup", "ControlGroup", "Include", "Status"}
    missing = required.difference(plan.columns)
    if missing:
        raise ValueError(f"comparison_plan is missing required columns: {sorted(missing)}")

    selected = plan.loc[
        plan["Include"].astype(str).str.strip().str.lower().isin(INCLUDE_TRUE_VALUES)
    ].copy()
    if selected.empty:
        return []

    invalid = selected.loc[selected["Status"].astype(str).str.lower() != "ready"]
    if not invalid.empty:
        labels = invalid.get("Comparison", pd.Series(index=invalid.index, dtype=object)).astype(str).tolist()
        raise ValueError(f"comparison_plan includes invalid comparisons: {labels[:8]}")

    if {"CaseN", "ControlN"}.issubset(selected.columns):
        too_small = selected.loc[
            (pd.to_numeric(selected["CaseN"], errors="coerce") < int(min_samples_per_group))
            | (pd.to_numeric(selected["ControlN"], errors="coerce") < int(min_samples_per_group))
        ]
        if not too_small.empty:
            labels = too_small.get("Comparison", pd.Series(index=too_small.index, dtype=object)).astype(str).tolist()
            raise ValueError(f"comparison_plan includes groups below min_samples_per_group: {labels[:8]}")

    return [
        (str(row["CaseGroup"]).strip(), str(row["ControlGroup"]).strip())
        for _, row in selected.iterrows()
    ]


def _validate_sample_alignment(otutab: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    sample_ids = [str(column) for column in otutab.columns]
    missing = [sample_id for sample_id in sample_ids if sample_id not in metadata.index]
    if missing:
        raise ValueError(
            "metadata is missing samples present in the OTU table: "
            f"{missing[:8]}"
        )
    return metadata.loc[sample_ids].copy()


def _relative_abundance_percent(otutab: pd.DataFrame) -> pd.DataFrame:
    library_sizes = otutab.sum(axis=0).replace(0, np.nan)
    return otutab.div(library_sizes, axis=1).fillna(0.0) * 100.0


def _counts_per_million(otutab: pd.DataFrame) -> pd.DataFrame:
    library_sizes = otutab.sum(axis=0).replace(0, np.nan)
    return otutab.div(library_sizes, axis=1).fillna(0.0) * 1_000_000.0


def _benjamini_hochberg(p_values: Iterable[float]) -> np.ndarray:
    values = np.asarray(list(p_values), dtype=float)
    values = np.nan_to_num(values, nan=1.0, posinf=1.0, neginf=1.0)
    values = np.clip(values, 0.0, 1.0)
    n = values.size
    if n == 0:
        return values

    order = np.argsort(values)
    ranked = values[order]
    adjusted = np.empty(n, dtype=float)
    running_min = 1.0
    for rank_index in range(n - 1, -1, -1):
        rank = rank_index + 1
        candidate = ranked[rank_index] * n / rank
        running_min = min(running_min, candidate)
        adjusted[rank_index] = running_min
    result = np.empty(n, dtype=float)
    result[order] = np.clip(adjusted, 0.0, 1.0)
    return result


def _test_feature(case_values: np.ndarray, control_values: np.ndarray, method: str) -> float:
    if method == "wilcox":
        if (
            case_values.size == control_values.size
            and case_values.size > 0
            and np.allclose(case_values, control_values)
            and np.allclose(case_values, case_values[0])
        ):
            return 1.0
        try:
            return float(stats.mannwhitneyu(case_values, control_values, alternative="two-sided").pvalue)
        except ValueError:
            return 1.0

    with np.errstate(invalid="ignore"):
        result = stats.ttest_ind(case_values, control_values, equal_var=False, nan_policy="omit")
    p_value = float(result.pvalue)
    return p_value if math.isfinite(p_value) else 1.0


def _merge_taxonomy_columns(result: pd.DataFrame, taxonomy: pd.DataFrame | None) -> pd.DataFrame:
    if taxonomy is None:
        return result
    available = [column for column in TAXONOMY_COLUMNS if column in taxonomy.columns]
    if not available:
        return result

    merged = result.merge(
        taxonomy.loc[:, ["OTUID", *available]],
        left_on="ID",
        right_on="OTUID",
        how="left",
    )
    merged = merged.drop(columns=["OTUID"])
    insert_at = list(merged.columns).index("Method") + 1
    for column in reversed(available):
        values = merged.pop(column).fillna("Unassigned")
        merged.insert(insert_at, column, values)
    return merged


def _run_single_comparison(
    otutab: pd.DataFrame,
    metadata: pd.DataFrame,
    taxonomy: pd.DataFrame | None,
    case_group: str,
    control_group: str,
    method: str,
    min_mean_relative_abundance: float,
    pvalue_threshold: float,
    fdr_threshold: float,
    log2fc_threshold: float,
    pseudo_count: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    case_samples = metadata.index[metadata["Group"] == case_group].tolist()
    control_samples = metadata.index[metadata["Group"] == control_group].tolist()
    selected_samples = [*case_samples, *control_samples]
    relative = _relative_abundance_percent(otutab)
    cpm = _counts_per_million(otutab)
    selected_relative = relative.loc[:, selected_samples].copy()

    mean_case = selected_relative.loc[:, case_samples].mean(axis=1)
    mean_control = selected_relative.loc[:, control_samples].mean(axis=1)
    mean_all = selected_relative.mean(axis=1)
    keep_mask = mean_all >= float(min_mean_relative_abundance)
    filtered_relative = selected_relative.loc[keep_mask].copy()
    if filtered_relative.empty:
        raise ValueError(
            "No features remain after min_mean_relative_abundance filtering. "
            "Lower the threshold and rerun."
        )

    p_values: list[float] = []
    for feature_id in filtered_relative.index:
        case_values = filtered_relative.loc[feature_id, case_samples].to_numpy(dtype=float)
        control_values = filtered_relative.loc[feature_id, control_samples].to_numpy(dtype=float)
        p_values.append(_test_feature(case_values, control_values, method))

    fdr_values = _benjamini_hochberg(p_values)
    mean_case = mean_case.loc[filtered_relative.index]
    mean_control = mean_control.loc[filtered_relative.index]
    log2fc = np.log2((mean_case + float(pseudo_count)) / (mean_control + float(pseudo_count)))
    log2cpm = np.log2(cpm.loc[filtered_relative.index, selected_samples].mean(axis=1) + 1.0)
    significant = (
        (np.asarray(p_values) <= float(pvalue_threshold))
        & (fdr_values <= float(fdr_threshold))
        & (np.abs(log2fc.to_numpy(dtype=float)) >= float(log2fc_threshold))
    )

    levels = np.where(
        significant & (log2fc.to_numpy(dtype=float) > 0),
        "Enriched",
        np.where(significant & (log2fc.to_numpy(dtype=float) < 0), "Depleted", "NotSignificant"),
    )
    result = pd.DataFrame(
        {
            "ID": filtered_relative.index.astype(str),
            "log2FC": log2fc.to_numpy(dtype=float),
            "log2CPM": log2cpm.to_numpy(dtype=float),
            "PValue": np.asarray(p_values, dtype=float),
            "FDR": fdr_values,
            "level": levels,
            "MeanCase": mean_case.to_numpy(dtype=float),
            "MeanControl": mean_control.to_numpy(dtype=float),
            "MeanCasePercent": mean_case.to_numpy(dtype=float),
            "MeanControlPercent": mean_control.to_numpy(dtype=float),
            "CaseGroup": case_group,
            "ControlGroup": control_group,
            "Method": method,
        }
    )
    for sample_id in selected_samples:
        result[sample_id] = filtered_relative[sample_id].to_numpy(dtype=float)
    result = _merge_taxonomy_columns(result, taxonomy)
    result = result.sort_values(
        ["FDR", "PValue", "log2FC"],
        ascending=[True, True, False],
        kind="stable",
    ).reset_index(drop=True)
    return result, selected_relative.loc[result["ID"].tolist(), selected_samples]


def _taxonomy_label(row: pd.Series) -> str:
    labels: list[str] = []
    for column in ("Phylum", "Class", "Order", "Family", "Genus", "Species"):
        value = row.get(column)
        if value is not None and str(value).strip() and str(value).strip() != "Unassigned":
            labels.append(f"{column}: {value}")
    return "<br>".join(labels) if labels else "Taxonomy: Unassigned"


def _build_volcano_figure(result: pd.DataFrame, comparison: str) -> Any:
    import plotly.graph_objects as go

    color_map = {
        "Enriched": "#D62728",
        "Depleted": "#2CA02C",
        "NotSignificant": "#A8B0BB",
    }
    fig = go.Figure()
    for level in ("Depleted", "NotSignificant", "Enriched"):
        subset = result.loc[result["level"] == level].copy()
        if subset.empty:
            continue
        customdata = np.stack(
            [
                subset["ID"].astype(str).to_numpy(),
                subset["PValue"].astype(float).to_numpy(),
                subset["FDR"].astype(float).to_numpy(),
                subset.apply(_taxonomy_label, axis=1).to_numpy(),
            ],
            axis=1,
        )
        fig.add_trace(
            go.Scattergl(
                x=subset["log2FC"],
                y=subset["log2CPM"],
                mode="markers",
                name=level,
                marker={
                    "color": color_map[level],
                    "size": 8 if level != "NotSignificant" else 6,
                    "opacity": 0.86 if level != "NotSignificant" else 0.55,
                    "line": {"width": 0},
                },
                customdata=customdata,
                hovertemplate=(
                    "Feature: %{customdata[0]}<br>"
                    "log2FC: %{x:.4f}<br>"
                    "log2CPM: %{y:.4f}<br>"
                    "PValue: %{customdata[1]:.3g}<br>"
                    "FDR: %{customdata[2]:.3g}<br>"
                    "%{customdata[3]}<extra></extra>"
                ),
            )
        )

    fig.add_vline(x=0, line_width=1, line_dash="dash", line_color="#59636E")
    fig.update_layout(
        title={"text": f"Differential Abundance - {comparison}", "x": 0.5},
        width=980,
        height=680,
        xaxis_title="log2 fold change (case / control)",
        yaxis_title="log2 count per million",
        legend_title_text="Differential level",
        margin={"l": 80, "r": 40, "t": 80, "b": 80},
    )
    apply_publication_theme(fig, width=980, height=680)
    return fig


def _normalize_heatmap_matrix(matrix: pd.DataFrame) -> pd.DataFrame:
    row_mean = matrix.mean(axis=1)
    row_std = matrix.std(axis=1, ddof=1).replace(0, np.nan)
    return matrix.sub(row_mean, axis=0).div(row_std, axis=0).fillna(0.0)


def _build_heatmap_figure(
    result: pd.DataFrame,
    matrix: pd.DataFrame,
    normalized: pd.DataFrame,
    comparison: str,
    used_fallback: bool,
) -> Any:
    import plotly.graph_objects as go

    row_info = result.set_index("ID").loc[normalized.index]
    row_labels = [
        f"{feature}<br>{row_info.loc[feature, 'level']}"
        for feature in normalized.index.astype(str)
    ]
    customdata = np.empty((normalized.shape[0], normalized.shape[1], 4), dtype=object)
    for row_index, feature_id in enumerate(normalized.index):
        taxonomy = _taxonomy_label(row_info.loc[feature_id])
        level = row_info.loc[feature_id, "level"]
        for col_index, sample_id in enumerate(normalized.columns):
            customdata[row_index, col_index] = [
                feature_id,
                level,
                float(matrix.loc[feature_id, sample_id]),
                taxonomy,
            ]

    title_suffix = "Top Differential Features"
    if used_fallback:
        title_suffix = "Top Differential Candidates (No Significant Features)"
    fig = go.Figure(
        data=go.Heatmap(
            z=normalized.to_numpy(dtype=float),
            x=normalized.columns.astype(str).tolist(),
            y=row_labels,
            zmid=0,
            colorscale="RdBu_r",
            colorbar={"title": "row z-score"},
            customdata=customdata,
            hovertemplate=(
                "Feature: %{customdata[0]}<br>"
                "Sample: %{x}<br>"
                "Level: %{customdata[1]}<br>"
                "Relative abundance: %{customdata[2]:.5f}%<br>"
                "%{customdata[3]}<br>"
                "z-score: %{z:.4f}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title={"text": f"{comparison} - {title_suffix}", "x": 0.5},
        width=1120,
        height=max(520, min(1800, 260 + normalized.shape[0] * 28)),
        xaxis_title="Sample",
        yaxis_title="Feature",
        margin={"l": min(380, 130 + max((len(str(x)) for x in normalized.index), default=0) * 5), "r": 80, "t": 80, "b": 110},
    )
    apply_publication_theme(fig, width=1120, height=int(fig.layout.height or 760))
    fig.update_xaxes(tickangle=45)
    fig.update_yaxes(autorange="reversed")
    return fig


def plot_differential_volcano(
    result_path: str,
    output_dir: str = DEFAULT_DIFFERENTIAL_VOLCANO_DIR,
    output_format: str = "html",
) -> dict[str, Any]:
    """Plot a volcano/MA-style chart from a differential result table."""

    output_format = validate_output_format(output_format)
    result = read_table(result_path, "differential_results")
    if "ID" not in result.columns:
        result = result.rename(columns={result.columns[0]: "ID"})
    required = {"ID", "log2FC", "log2CPM", "PValue", "FDR", "level"}
    missing = required.difference(result.columns)
    if missing:
        raise ValueError(f"differential result table is missing columns: {sorted(missing)}")

    comparison = os.path.splitext(os.path.basename(result_path))[0].replace("_differential_results", "")
    if comparison == "differential_results":
        comparison = os.path.basename(os.path.dirname(os.path.abspath(result_path)))
    resolved_output_dir = ensure_output_dir(os.path.join(output_dir, sanitize_id(comparison)))
    generated_files: list[str] = []
    skipped_static: list[str] = []
    fig = _build_volcano_figure(result, comparison)
    base_path = os.path.join(resolved_output_dir, "volcano")
    if output_format in {"html", "all"}:
        generated_files.append(write_html_figure(fig, f"{base_path}.html"))
    write_optional_static(fig, base_path, output_format, 980, 680, generated_files, skipped_static)
    return {
        "result_path": os.path.abspath(result_path),
        "output_dir": resolved_output_dir,
        "plots": generated_files,
        "skipped_static_exports": skipped_static,
    }


def plot_differential_heatmap(
    result_path: str,
    output_dir: str = DEFAULT_DIFFERENTIAL_HEATMAP_DIR,
    output_format: str = "html",
    top_n: int = 30,
) -> dict[str, Any]:
    """Plot a differential abundance heatmap from a differential result table."""

    output_format = validate_output_format(output_format)
    result = read_table(result_path, "differential_results")
    if "ID" not in result.columns:
        result = result.rename(columns={result.columns[0]: "ID"})
    non_sample_columns = {
        "ID",
        "log2FC",
        "log2CPM",
        "PValue",
        "FDR",
        "level",
        "MeanCase",
        "MeanControl",
        "MeanCasePercent",
        "MeanControlPercent",
        "CaseGroup",
        "ControlGroup",
        "Method",
        *TAXONOMY_COLUMNS,
    }
    sample_columns = [column for column in result.columns if column not in non_sample_columns]
    if not sample_columns:
        raise ValueError("differential result table has no sample abundance columns.")

    comparison = os.path.splitext(os.path.basename(result_path))[0].replace("_differential_results", "")
    if comparison == "differential_results":
        comparison = os.path.basename(os.path.dirname(os.path.abspath(result_path)))
    selected, used_fallback = _select_heatmap_features(result, int(top_n))
    matrix = selected.set_index("ID").loc[:, sample_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    normalized = _normalize_heatmap_matrix(matrix)
    resolved_output_dir = ensure_output_dir(os.path.join(output_dir, sanitize_id(comparison)))
    generated_files: list[str] = []
    skipped_static: list[str] = []

    matrix_table = normalized.copy()
    matrix_table.insert(0, "ID", matrix_table.index)
    generated_files.append(
        write_table(
            matrix_table,
            os.path.join(resolved_output_dir, "heatmap_matrix_zscore.tsv"),
            include_index=False,
        )
    )
    fig = _build_heatmap_figure(selected, matrix, normalized, comparison, used_fallback)
    base_path = os.path.join(resolved_output_dir, "heatmap")
    if output_format in {"html", "all"}:
        generated_files.append(write_html_figure(fig, f"{base_path}.html"))
    write_optional_static(
        fig,
        base_path,
        output_format,
        width=1120,
        height=int(fig.layout.height or 760),
        generated_files=generated_files,
        skipped_static=skipped_static,
    )
    return {
        "result_path": os.path.abspath(result_path),
        "output_dir": resolved_output_dir,
        "used_fallback": used_fallback,
        "plots": generated_files,
        "skipped_static_exports": skipped_static,
    }


def _select_heatmap_features(result: pd.DataFrame, top_n: int) -> tuple[pd.DataFrame, bool]:
    top_n = max(1, int(top_n))
    significant = result.loc[result["level"].isin(["Enriched", "Depleted"])].copy()
    if significant.empty:
        selected = result.copy()
        used_fallback = True
    else:
        selected = significant
        used_fallback = False
    selected["_abs_log2FC"] = pd.to_numeric(selected["log2FC"], errors="coerce").abs()
    selected["FDR"] = pd.to_numeric(selected["FDR"], errors="coerce").fillna(1.0)
    selected["PValue"] = pd.to_numeric(selected["PValue"], errors="coerce").fillna(1.0)
    selected = selected.sort_values(
        ["FDR", "PValue", "_abs_log2FC"],
        ascending=[True, True, False],
        kind="stable",
    ).head(top_n)
    return selected.drop(columns=["_abs_log2FC"]), used_fallback


def run_taxonomy_differential_abundance(
    otutab_path: str = os.path.join(DEFAULT_FINAL_DIR, "otutab.txt"),
    metadata_path: str = os.path.join("work", "00_input", "metadata.txt"),
    output_dir: str = DEFAULT_DIFFERENTIAL_OUTPUT_DIR,
    group_col: str = "Group",
    sample_id_col: str = "SampleID",
    comparisons: Sequence[Any] | str | None = None,
    reference_group: str | None = None,
    comparison_plan_path: str | None = None,
    run_confirmed_plan: bool = False,
    method: str = "wilcox",
    min_mean_relative_abundance: float = 0.001,
    pvalue: float = 0.05,
    fdr: float = 0.2,
    log2fc_threshold: float = 0.0,
    taxonomy_path: str | None = os.path.join(DEFAULT_FINAL_DIR, "taxonomy.tsv"),
    output_format: str = "html",
    min_samples_per_group: int = 2,
    top_n_heatmap: int = 30,
    pseudo_count: float = 1e-6,
) -> dict[str, Any]:
    """Run pairwise differential abundance analysis and generate plots.

    Direction is always CASE versus CONTROL. Positive log2FC means the feature
    has higher mean relative abundance in the case group.
    """

    method = _normalize_method(method)
    output_format = validate_output_format(output_format)
    resolved_output_dir = ensure_output_dir(output_dir)
    generated_files: list[str] = []
    skipped_static: list[str] = []

    if comparison_plan_path:
        plan_path = os.path.abspath(comparison_plan_path)
        generated_files.append(plan_path)
        if not run_confirmed_plan:
            return {
                "status": "confirmation_required",
                "analysis_ran": False,
                "message": "Set run_confirmed_plan=True after marking Include=yes in the comparison plan.",
                "comparison_plan": plan_path,
                "generated_files": generated_files,
                "skipped_static_exports": skipped_static,
            }
        selected_comparisons = _load_confirmed_plan(plan_path, min_samples_per_group)
        plan_rows = read_table(plan_path, "comparison_plan").to_dict(orient="records")
    else:
        plan_result = build_differential_comparison_plan(
            metadata_path=metadata_path,
            output_dir=resolved_output_dir,
            group_col=group_col,
            sample_id_col=sample_id_col,
            comparisons=comparisons,
            reference_group=reference_group,
            min_samples_per_group=min_samples_per_group,
        )
        generated_files.append(plan_result["comparison_plan"])
        plan_path = plan_result["comparison_plan"]
        plan_rows = plan_result["plan"]
        selected_comparisons = [
            (row["CaseGroup"], row["ControlGroup"])
            for row in plan_rows
            if str(row["Include"]).lower() in INCLUDE_TRUE_VALUES and row["Status"] == "ready"
        ]

    if not selected_comparisons:
        return {
            "status": "plan_required",
            "analysis_ran": False,
            "message": (
                "No confirmed comparisons were supplied. Edit comparison_plan.tsv "
                "or rerun with --compare CASE:CONTROL or --reference-group GROUP."
            ),
            "output_dir": resolved_output_dir,
            "comparison_plan": plan_path,
            "comparisons": plan_rows,
            "generated_files": generated_files,
            "skipped_static_exports": skipped_static,
        }

    metadata = _read_group_metadata(metadata_path, sample_id_col=sample_id_col, group_col=group_col)
    otutab = _read_otutab(otutab_path)
    metadata = _validate_sample_alignment(otutab, metadata)
    taxonomy = _read_taxonomy(taxonomy_path)

    comparison_results: dict[str, Any] = {}
    for case_group, control_group in selected_comparisons:
        case_n = int((metadata["Group"] == case_group).sum())
        control_n = int((metadata["Group"] == control_group).sum())
        if case_n < int(min_samples_per_group) or control_n < int(min_samples_per_group):
            raise ValueError(
                f"Comparison {case_group} vs {control_group} has insufficient aligned samples: "
                f"case n={case_n}, control n={control_n}, "
                f"min_samples_per_group={min_samples_per_group}."
            )

        comparison = _comparison_label(case_group, control_group)
        safe_comparison = sanitize_id(comparison)
        result, selected_relative = _run_single_comparison(
            otutab=otutab,
            metadata=metadata,
            taxonomy=taxonomy,
            case_group=case_group,
            control_group=control_group,
            method=method,
            min_mean_relative_abundance=min_mean_relative_abundance,
            pvalue_threshold=pvalue,
            fdr_threshold=fdr,
            log2fc_threshold=log2fc_threshold,
            pseudo_count=pseudo_count,
        )

        result_dir = ensure_output_dir(os.path.join(resolved_output_dir, "comparison_result", safe_comparison))
        result_path = write_table(
            result,
            os.path.join(result_dir, "differential_results.tsv"),
            include_index=False,
        )
        significant_path = write_table(
            result.loc[result["level"].isin(["Enriched", "Depleted"])],
            os.path.join(result_dir, "differential_results_significant.tsv"),
            include_index=False,
        )
        relative_table = selected_relative.copy()
        relative_table.insert(0, "ID", relative_table.index)
        relative_path = write_table(
            relative_table,
            os.path.join(result_dir, "relative_abundance_percent.tsv"),
            include_index=False,
        )
        generated_files.extend([result_path, significant_path, relative_path])

        volcano = plot_differential_volcano(
            result_path=result_path,
            output_dir=os.path.join(resolved_output_dir, "volcano_chart"),
            output_format=output_format,
        )
        heatmap = plot_differential_heatmap(
            result_path=result_path,
            output_dir=os.path.join(resolved_output_dir, "heatmap_chart"),
            output_format=output_format,
            top_n=top_n_heatmap,
        )
        generated_files.extend(volcano["plots"])
        generated_files.extend(heatmap["plots"])
        skipped_static.extend(volcano["skipped_static_exports"])
        skipped_static.extend(heatmap["skipped_static_exports"])
        comparison_results[comparison] = {
            "case_group": case_group,
            "control_group": control_group,
            "result_dir": result_dir,
            "result_table": result_path,
            "significant_table": significant_path,
            "relative_abundance_table": relative_path,
            "volcano": volcano,
            "heatmap": heatmap,
            "features_tested": int(result.shape[0]),
            "significant_features": int(result["level"].isin(["Enriched", "Depleted"]).sum()),
        }

    return {
        "status": "completed",
        "analysis_ran": True,
        "method": method,
        "otutab": os.path.abspath(otutab_path),
        "metadata": os.path.abspath(metadata_path),
        "taxonomy": None if taxonomy is None else os.path.abspath(str(taxonomy_path)),
        "output_dir": resolved_output_dir,
        "comparison_plan": plan_path,
        "comparisons": comparison_results,
        "generated_files": list(dict.fromkeys(generated_files)),
        "skipped_static_exports": skipped_static,
        "thresholds": {
            "min_mean_relative_abundance_percent": float(min_mean_relative_abundance),
            "pvalue": float(pvalue),
            "fdr": float(fdr),
            "log2fc": float(log2fc_threshold),
        },
    }


TOOL_DEFINITIONS = [
    {
        "name": "build_differential_comparison_plan",
        "description": (
            "Build and validate a pairwise differential abundance comparison plan "
            "from metadata. Without explicit comparisons or a reference group, "
            "writes candidate comparisons with Include=no for user confirmation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "metadata_path": {"type": "string"},
                "output_dir": {"type": "string", "default": DEFAULT_DIFFERENTIAL_OUTPUT_DIR},
                "group_col": {"type": "string", "default": "Group"},
                "sample_id_col": {"type": "string", "default": "SampleID"},
                "comparisons": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Repeatable CASE:CONTROL or CASE_vs_CONTROL comparison definitions.",
                },
                "reference_group": {"type": "string"},
                "min_samples_per_group": {"type": "integer", "default": 2},
            },
            "required": ["metadata_path"],
        },
        "fn": build_differential_comparison_plan,
    },
    {
        "name": "run_taxonomy_differential_abundance",
        "description": (
            "Run pairwise Wilcoxon/t-test differential abundance from an OTU/ASV table "
            "and metadata, then write result tables, volcano charts, and heatmaps under "
            "work/06_final/statistics/differential by default."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "otutab_path": {"type": "string", "default": os.path.join(DEFAULT_FINAL_DIR, "otutab.txt")},
                "metadata_path": {"type": "string", "default": os.path.join("work", "00_input", "metadata.txt")},
                "output_dir": {"type": "string", "default": DEFAULT_DIFFERENTIAL_OUTPUT_DIR},
                "group_col": {"type": "string", "default": "Group"},
                "sample_id_col": {"type": "string", "default": "SampleID"},
                "comparisons": {"type": "array", "items": {"type": "string"}},
                "reference_group": {"type": "string"},
                "comparison_plan_path": {"type": "string"},
                "run_confirmed_plan": {"type": "boolean", "default": False},
                "method": {"type": "string", "enum": ["wilcox", "t.test"], "default": "wilcox"},
                "min_mean_relative_abundance": {"type": "number", "default": 0.001},
                "pvalue": {"type": "number", "default": 0.05},
                "fdr": {"type": "number", "default": 0.2},
                "log2fc_threshold": {"type": "number", "default": 0.0},
                "taxonomy_path": {"type": "string", "default": os.path.join(DEFAULT_FINAL_DIR, "taxonomy.tsv")},
                "output_format": {
                    "type": "string",
                    "enum": ["html", "png", "pdf", "svg", "all"],
                    "default": "html",
                },
                "min_samples_per_group": {"type": "integer", "default": 2},
                "top_n_heatmap": {"type": "integer", "default": 30},
            },
        },
        "fn": run_taxonomy_differential_abundance,
    },
    {
        "name": "plot_differential_volcano",
        "description": "Plot a differential abundance volcano chart from a differential_results.tsv table.",
        "parameters": {
            "type": "object",
            "properties": {
                "result_path": {"type": "string"},
                "output_dir": {"type": "string", "default": DEFAULT_DIFFERENTIAL_VOLCANO_DIR},
                "output_format": {
                    "type": "string",
                    "enum": ["html", "png", "pdf", "svg", "all"],
                    "default": "html",
                },
            },
            "required": ["result_path"],
        },
        "fn": plot_differential_volcano,
    },
    {
        "name": "plot_differential_heatmap",
        "description": "Plot a differential abundance heatmap from a differential_results.tsv table.",
        "parameters": {
            "type": "object",
            "properties": {
                "result_path": {"type": "string"},
                "output_dir": {"type": "string", "default": DEFAULT_DIFFERENTIAL_HEATMAP_DIR},
                "output_format": {
                    "type": "string",
                    "enum": ["html", "png", "pdf", "svg", "all"],
                    "default": "html",
                },
                "top_n": {"type": "integer", "default": 30},
            },
            "required": ["result_path"],
        },
        "fn": plot_differential_heatmap,
    },
]
