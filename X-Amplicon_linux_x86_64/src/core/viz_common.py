"""Shared helpers for X-Amplicon visualization tools."""

from __future__ import annotations

try:
    import matplotlib
except ModuleNotFoundError:
    matplotlib = None
else:
    matplotlib.use("Agg")

import os
import re
from collections.abc import Mapping
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

DEFAULT_PLOTS_DIR = os.path.join("work", "06_final", "plots")
DEFAULT_FINAL_DIR = os.path.join("work", "06_final")
DEFAULT_ALPHA_BOXPLOT_DIR = os.path.join(DEFAULT_PLOTS_DIR, "alpha_boxplot_chart")
DEFAULT_ALPHA_BARPLOT_DIR = os.path.join(DEFAULT_PLOTS_DIR, "alpha_barplot_chart")
DEFAULT_ALPHA_RAREFACTION_DIR = os.path.join(DEFAULT_PLOTS_DIR, "alpha_rare_chart")
DEFAULT_BETA_PCOA_DIR = os.path.join(DEFAULT_PLOTS_DIR, "beta_pcoa_chart")
DEFAULT_BETA_CPCOA_DIR = os.path.join(DEFAULT_PLOTS_DIR, "beta_cpcoa_chart")
DEFAULT_BETA_HEATMAP_DIR = os.path.join(DEFAULT_PLOTS_DIR, "beta_heatmap_chart")
DEFAULT_TAXONOMY_STACKED_BAR_DIR = os.path.join(DEFAULT_PLOTS_DIR, "taxonomy_stacked_bar_chart")
DEFAULT_TAXONOMY_HEATMAP_DIR = os.path.join(DEFAULT_PLOTS_DIR, "taxonomy_heatmap_chart")
VALID_OUTPUT_FORMATS = {"html", "png", "pdf", "svg", "all"}
STATIC_OUTPUT_FORMATS = ("png", "pdf", "svg")
DEFAULT_TAXONOMY_LEVELS = (
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
)
DEFAULT_BETA_METRICS = (
    "braycurtis",
    "euclidean",
    "jaccard",
    "manhattan",
    "unweighted_unifrac",
    "weighted_unifrac",
)
ALPHA_METRIC_ALIASES = {
    "richness": ("richness", "Observed_OTUs", "Observed", "ObservedOTUs", "sobs"),
    "chao1": ("chao1", "Chao1"),
    "ACE": ("ACE", "ace"),
    "shannon": ("shannon", "Shannon"),
    "simpson": ("simpson", "Simpson"),
    "invsimpson": (
        "invsimpson",
        "InvSimpson",
        "InverseSimpson",
        "inverse_simpson",
        "inv_simpson",
    ),
}
DEFAULT_ALPHA_METRICS = tuple(ALPHA_METRIC_ALIASES)
SUMMARY_COLUMNS = {"all", "total", "sum", "overall"}
GROUP_COLORS = {
    "KO": "#5B8FF9",
    "OE": "#F6BD16",
    "WT": "#5AD8A6",
}
DEFAULT_GROUP_ORDER = (
    "WT",
    "Control",
    "CTRL",
    "CON",
    "CK",
    "KO",
    "OE",
)
PUBLICATION_FONT_FAMILY = "Arial, Helvetica, sans-serif"
PUBLICATION_COLORWAY = (
    "#4E79A7",
    "#F28E2B",
    "#59A14F",
    "#E15759",
    "#76B7B2",
    "#EDC948",
    "#B07AA1",
    "#FF9DA7",
    "#9C755F",
    "#BAB0AC",
)


def ensure_output_dir(output_dir: str | None = None) -> str:
    """Resolve and create an output directory."""

    resolved_dir = os.path.abspath(output_dir or DEFAULT_PLOTS_DIR)
    os.makedirs(resolved_dir, exist_ok=True)
    return resolved_dir


def validate_output_format(output_format: str) -> str:
    """Normalize and validate a visualization output format."""

    normalized = str(output_format).strip().lower()
    if normalized not in VALID_OUTPUT_FORMATS:
        raise ValueError(
            "output_format must be one of: "
            f"{sorted(VALID_OUTPUT_FORMATS)}"
        )
    return normalized


def ensure_file(path: str, label: str) -> str:
    """Validate and resolve an input file path."""

    if not path:
        raise ValueError(f"{label} is required.")

    resolved_path = os.path.abspath(path)
    if not os.path.isfile(resolved_path):
        raise FileNotFoundError(f"{label} not found: {resolved_path}")
    return resolved_path


def maybe_file(path: str | None) -> str | None:
    """Return an absolute file path when it exists, otherwise None."""

    if path is None:
        return None
    text = str(path).strip()
    if not text:
        return None
    resolved_path = os.path.abspath(text)
    return resolved_path if os.path.isfile(resolved_path) else None


def infer_delimiter(path: str) -> str:
    """Infer a CSV/TSV delimiter from extension or the first line."""

    suffix = os.path.splitext(path)[1].lower()
    if suffix == ".csv":
        return ","
    if suffix in {".tsv", ".txt"}:
        return "\t"

    with open(path, "r", encoding="utf-8", errors="ignore", newline=None) as handle:
        header = handle.readline()
    return "\t" if header.count("\t") >= header.count(",") else ","


def read_table(path: str, label: str, index_col: int | str | None = None) -> pd.DataFrame:
    """Read a delimited table with common encodings and cleaned column names."""

    resolved_path = ensure_file(path, label)
    delimiter = infer_delimiter(resolved_path)
    last_error: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312", "latin1"):
        try:
            table = pd.read_csv(
                resolved_path,
                sep=delimiter,
                encoding=encoding,
                index_col=index_col,
            )
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        except Exception as exc:
            last_error = exc
            continue

        if table.empty:
            raise ValueError(f"{label} is empty: {resolved_path}")
        table.columns = [str(column).strip() for column in table.columns]
        if table.index.name is not None:
            table.index.name = str(table.index.name).strip()
        return table

    raise ValueError(f"Failed to read {label}: {resolved_path}; last error: {last_error}")


def write_table(table: pd.DataFrame, path: str, include_index: bool = True) -> str:
    """Write a TSV file and return its absolute path."""

    resolved_path = os.path.abspath(path)
    parent_dir = os.path.dirname(resolved_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    table.to_csv(resolved_path, sep="\t", index=include_index, encoding="utf-8-sig")
    return resolved_path


def write_html_figure(fig: Any, path: str) -> str:
    """Write a Plotly figure as an offline HTML file."""

    resolved_path = os.path.abspath(path)
    parent_dir = os.path.dirname(resolved_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    fig.write_html(
        resolved_path,
        include_plotlyjs=True,
        full_html=True,
        config={"responsive": True, "displaylogo": False},
    )
    return resolved_path


def write_static_figure(fig: Any, path: str, width: int, height: int, scale: float = 2.0) -> str | None:
    """Write a Plotly static image when kaleido is available."""

    resolved_path = os.path.abspath(path)
    parent_dir = os.path.dirname(resolved_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    try:
        fig.write_image(resolved_path, width=width, height=height, scale=scale)
    except Exception:
        return None
    return resolved_path


def write_optional_static(
    fig: Any,
    base_path: str,
    output_format: str,
    width: int,
    height: int,
    generated_files: list[str],
    skipped_static: list[str],
    scale: float = 2.0,
) -> None:
    """Write requested Plotly static formats and track skipped kaleido exports."""

    output_format = validate_output_format(output_format)
    if output_format not in {*STATIC_OUTPUT_FORMATS, "all"}:
        return

    for suffix in STATIC_OUTPUT_FORMATS:
        if output_format not in {suffix, "all"}:
            continue
        static_path = f"{base_path}.{suffix}"
        written = write_static_figure(
            fig,
            static_path,
            width=width,
            height=height,
            scale=scale,
        )
        if written is None:
            skipped_static.append(static_path)
        else:
            generated_files.append(written)


def write_html_dashboard(figures: dict[str, Any], path: str, title: str) -> str:
    """Write multiple Plotly figures to one offline tabbed HTML dashboard."""

    import html

    resolved_path = os.path.abspath(path)
    parent_dir = os.path.dirname(resolved_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    tabs: list[str] = []
    panels: list[str] = []
    for index, (name, fig) in enumerate(figures.items()):
        tab_id = sanitize_id(name)
        active_class = " active" if index == 0 else ""
        display = "block" if index == 0 else "none"
        tabs.append(
            f'<button class="tab-button{active_class}" onclick="openTab(\'{tab_id}\', this)">'
            f"{html.escape(str(name))}</button>"
        )
        panels.append(
            f'<section id="{tab_id}" class="tab-panel" style="display:{display};">'
            + fig.to_html(
                full_html=False,
                include_plotlyjs=True if index == 0 else False,
                div_id=f"fig_{tab_id}",
                config={"responsive": True, "displaylogo": False},
            )
            + "</section>"
        )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    body {{
      margin: 0;
      padding: 18px 22px 28px;
      font-family: "Segoe UI", Arial, sans-serif;
      color: #202733;
      background: #f6f7f9;
    }}
    h1 {{ margin: 0 0 14px; font-size: 24px; font-weight: 650; }}
    .tabs {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }}
    .tab-button {{
      border: 1px solid #c9d1d9;
      background: #ffffff;
      color: #202733;
      padding: 8px 14px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 14px;
    }}
    .tab-button.active {{ background: #202733; color: #ffffff; border-color: #202733; }}
    .tab-panel {{
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 8px;
    }}
  </style>
  <script>
    function openTab(tabId, btn) {{
      document.querySelectorAll('.tab-panel').forEach(function(panel) {{
        panel.style.display = 'none';
      }});
      document.querySelectorAll('.tab-button').forEach(function(button) {{
        button.classList.remove('active');
      }});
      document.getElementById(tabId).style.display = 'block';
      btn.classList.add('active');
      window.dispatchEvent(new Event('resize'));
    }}
  </script>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <nav class="tabs">{''.join(tabs)}</nav>
  {''.join(panels)}
</body>
</html>
"""
    with open(resolved_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(page)
    return resolved_path


def sanitize_id(text: str) -> str:
    """Convert text to a safe id or filename fragment."""

    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(text)).strip("_") or "item"


def natural_sort_key(text: str) -> tuple[Any, ...]:
    """Return a natural-sort key that keeps numeric suffixes in numeric order."""

    parts = re.split(r"(\d+)", str(text))
    key: list[Any] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part.casefold())
    return tuple(key)


def sort_groups(
    groups: Iterable[str],
    preferred_order: Sequence[str] | None = DEFAULT_GROUP_ORDER,
) -> list[str]:
    """Return stable, publication-friendly group order for legends and axes."""

    unique_groups = list(dict.fromkeys(str(group) for group in groups if str(group).strip()))
    preferred = {
        str(group).casefold(): index
        for index, group in enumerate(preferred_order or ())
    }

    def _key(group: str) -> tuple[int, int, tuple[Any, ...]]:
        rank = preferred.get(group.casefold())
        if rank is None:
            return 1, len(preferred), natural_sort_key(group)
        return 0, rank, natural_sort_key(group)

    return sorted(unique_groups, key=_key)


def sort_samples_by_metadata(
    sample_ids: Iterable[str],
    sample_metadata: pd.DataFrame | None = None,
) -> list[str]:
    """Sort samples by metadata group order and natural sample ID order."""

    sample_list = [str(sample_id) for sample_id in sample_ids]
    if sample_metadata is None or sample_metadata.empty:
        return sort_sample_ids(sample_list)

    metadata = sample_metadata.copy()
    if "SampleID" not in metadata.columns or "Group" not in metadata.columns:
        return sort_sample_ids(sample_list)
    metadata = metadata.set_index("SampleID", drop=False)
    group_map = {
        str(sample_id): str(metadata.loc[sample_id, "Group"])
        for sample_id in sample_list
        if sample_id in metadata.index
    }
    group_order = sort_groups(group_map.values())
    group_rank = {group: index for index, group in enumerate(group_order)}

    def _key(sample_id: str) -> tuple[int, tuple[Any, ...]]:
        group = group_map.get(sample_id, infer_group(sample_id))
        return group_rank.get(group, len(group_rank)), natural_sort_key(sample_id)

    return sorted(sample_list, key=_key)


def parse_color_palette(
    color_palette: str | Sequence[str] | Mapping[str, str] | None,
) -> tuple[dict[str, str], list[str]]:
    """Parse a user palette into named color overrides and sequential colors."""

    if color_palette is None:
        return {}, []
    if isinstance(color_palette, Mapping):
        return {
            str(key).strip(): str(value).strip()
            for key, value in color_palette.items()
            if str(key).strip() and str(value).strip()
        }, []
    if isinstance(color_palette, str):
        tokens = [
            token.strip()
            for token in re.split(r"[,;\n]+", color_palette)
            if token.strip()
        ]
    else:
        tokens = [str(token).strip() for token in color_palette if str(token).strip()]

    named: dict[str, str] = {}
    sequential: list[str] = []
    for token in tokens:
        if ":" in token and not token.startswith("#"):
            key, value = token.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key and value:
                named[key] = value
        else:
            sequential.append(token)
    return named, sequential


def resolve_color_palette(
    values: Iterable[str],
    color_palette: str | Sequence[str] | Mapping[str, str] | None = None,
    default_mapping: Mapping[str, str] | None = GROUP_COLORS,
    sort_values: bool = True,
) -> dict[str, str]:
    """Resolve colors for group or taxon names with optional user overrides."""

    ordered_values = (
        sort_groups(values)
        if sort_values
        else list(dict.fromkeys(str(value) for value in values))
    )
    named, sequential = parse_color_palette(color_palette)
    fallback = plotly_palette()
    defaults = {str(key): str(value) for key, value in (default_mapping or {}).items()}
    colors: dict[str, str] = {}

    for index, value in enumerate(ordered_values):
        text = str(value)
        if text in named:
            colors[text] = named[text]
        elif sequential:
            colors[text] = sequential[index % len(sequential)]
        elif text in defaults:
            colors[text] = defaults[text]
        else:
            colors[text] = fallback[index % len(fallback)]
    return colors


def apply_publication_theme(
    fig: Any,
    width: int | None = None,
    height: int | None = None,
) -> Any:
    """Apply the shared X-Amplicon publication-style Plotly theme."""

    layout_updates: dict[str, Any] = {
        "template": "plotly_white",
        "font": {
            "family": PUBLICATION_FONT_FAMILY,
            "size": 14,
            "color": "#202733",
        },
        "title": {
            "font": {"family": PUBLICATION_FONT_FAMILY, "size": 21, "color": "#202733"},
            "x": 0.5,
            "xanchor": "center",
        },
        "paper_bgcolor": "#ffffff",
        "plot_bgcolor": "#ffffff",
        "colorway": list(PUBLICATION_COLORWAY),
        "legend": {
            "bgcolor": "rgba(255,255,255,0.88)",
            "bordercolor": "#D8DEE6",
            "borderwidth": 1,
            "font": {"family": PUBLICATION_FONT_FAMILY, "size": 12},
        },
        "hoverlabel": {
            "font": {"family": PUBLICATION_FONT_FAMILY, "size": 12},
            "bgcolor": "#ffffff",
        },
    }
    if width is not None:
        layout_updates["width"] = int(width)
    if height is not None:
        layout_updates["height"] = int(height)
    fig.update_layout(**layout_updates)
    fig.update_xaxes(
        showline=True,
        linewidth=1,
        linecolor="#30343B",
        mirror=True,
        ticks="outside",
        tickcolor="#30343B",
        gridcolor="#E7EBF0",
        zerolinecolor="#B8C0CC",
        title_font={"family": PUBLICATION_FONT_FAMILY, "size": 14},
        tickfont={"family": PUBLICATION_FONT_FAMILY, "size": 12},
    )
    fig.update_yaxes(
        showline=True,
        linewidth=1,
        linecolor="#30343B",
        mirror=True,
        ticks="outside",
        tickcolor="#30343B",
        gridcolor="#E7EBF0",
        zerolinecolor="#B8C0CC",
        title_font={"family": PUBLICATION_FONT_FAMILY, "size": 14},
        tickfont={"family": PUBLICATION_FONT_FAMILY, "size": 12},
    )
    return fig


def write_chart_index(
    output_dir: str,
    title: str,
    generated_files: Sequence[str],
    description: str | None = None,
) -> str:
    """Write a lightweight HTML index for one chart directory."""

    import html

    resolved_output_dir = ensure_output_dir(output_dir)
    rows: list[str] = []
    for path in generated_files:
        resolved_path = os.path.abspath(str(path))
        if not os.path.isfile(resolved_path):
            continue
        try:
            relative_path = os.path.relpath(resolved_path, resolved_output_dir)
        except ValueError:
            relative_path = resolved_path
        href_path = relative_path.replace(os.sep, "/")
        suffix = os.path.splitext(resolved_path)[1].lstrip(".").upper() or "FILE"
        size_kb = os.path.getsize(resolved_path) / 1024.0
        rows.append(
            "<tr>"
            f"<td>{html.escape(suffix)}</td>"
            f'<td><a href="{html.escape(href_path)}">{html.escape(relative_path)}</a></td>'
            f"<td>{size_kb:.1f} KB</td>"
            "</tr>"
        )

    if not rows:
        rows.append('<tr><td colspan="3">No generated files are available.</td></tr>')

    description_html = (
        f"<p>{html.escape(description)}</p>"
        if description
        else ""
    )
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    body {{
      margin: 0;
      padding: 24px 28px 34px;
      font-family: {PUBLICATION_FONT_FAMILY};
      color: #202733;
      background: #ffffff;
    }}
    h1 {{ margin: 0 0 8px; font-size: 25px; font-weight: 650; }}
    p {{ margin: 0 0 18px; color: #4B5563; max-width: 920px; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 1120px; }}
    th, td {{ border-bottom: 1px solid #E5E7EB; padding: 10px 12px; text-align: left; }}
    th {{ background: #F6F7F9; color: #202733; font-weight: 650; }}
    td:first-child {{ width: 90px; color: #59636E; font-weight: 650; }}
    td:last-child {{ width: 110px; color: #59636E; }}
    a {{ color: #2F6B9A; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  {description_html}
  <table>
    <thead><tr><th>Type</th><th>File</th><th>Size</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""
    return write_text_file(os.path.join(resolved_output_dir, "index.html"), page)


def write_text_file(path: str, content: str) -> str:
    """Write UTF-8 text and return the absolute path."""

    resolved_path = os.path.abspath(path)
    parent_dir = os.path.dirname(resolved_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    with open(resolved_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return resolved_path


def infer_group(sample_id: str) -> str:
    """Infer a group label from a sample id by removing trailing digits."""

    text = str(sample_id).strip()
    match = re.match(r"^(.+?)(\d+)$", text)
    return match.group(1) if match else text


def read_metadata(
    metadata_path: str | None,
    sample_id_col: str = "SampleID",
    group_col: str = "Group",
) -> pd.DataFrame | None:
    """Read sample metadata and normalize sample/group columns."""

    resolved_metadata_path = maybe_file(metadata_path)
    if resolved_metadata_path is None:
        return None

    table = read_table(resolved_metadata_path, "metadata")
    lower_map = {str(column).strip().lower(): column for column in table.columns}
    sample_column = (
        table.columns[0]
        if sample_id_col not in table.columns
        else sample_id_col
    )
    sample_column = lower_map.get(str(sample_id_col).lower(), sample_column)
    group_column = lower_map.get(str(group_col).lower(), lower_map.get("group"))
    if group_column is None:
        raise ValueError(
            f"metadata is missing group column '{group_col}': {resolved_metadata_path}"
        )

    metadata = table[[sample_column, group_column]].copy()
    metadata = metadata.rename(columns={sample_column: "SampleID", group_column: "Group"})
    metadata["SampleID"] = metadata["SampleID"].astype(str).str.strip()
    metadata["Group"] = metadata["Group"].astype(str).str.strip()
    metadata = metadata.loc[metadata["SampleID"] != ""].copy()

    conflicts = metadata.groupby("SampleID")["Group"].nunique()
    conflicts = conflicts.loc[conflicts > 1]
    if not conflicts.empty:
        raise ValueError(
            "metadata contains conflicting groups for samples: "
            f"{conflicts.index.tolist()[:8]}"
        )

    metadata = metadata.drop_duplicates(subset=["SampleID"], keep="first")
    metadata = metadata.set_index("SampleID", drop=False)
    return metadata


def build_sample_metadata(
    sample_ids: Sequence[str],
    metadata_path: str | None = None,
    sample_id_col: str = "SampleID",
    group_col: str = "Group",
) -> pd.DataFrame:
    """Build sample metadata, using file metadata when available."""

    sample_ids = [str(sample_id) for sample_id in sample_ids]
    metadata = read_metadata(metadata_path, sample_id_col=sample_id_col, group_col=group_col)
    if metadata is None:
        return pd.DataFrame(
            {
                "SampleID": sample_ids,
                "Group": [infer_group(sample_id) for sample_id in sample_ids],
            }
        )

    missing_samples = [sample_id for sample_id in sample_ids if sample_id not in metadata.index]
    if missing_samples:
        raise ValueError(
            "metadata is missing samples required by the table: "
            f"{missing_samples[:8]}"
        )

    return metadata.loc[sample_ids, ["SampleID", "Group"]].reset_index(drop=True)


def normalize_alpha_table(alpha_path: str) -> pd.DataFrame:
    """Read and normalize an alpha diversity table."""

    table = read_table(alpha_path, "alpha_diversity")
    columns = list(table.columns)
    if not columns:
        raise ValueError(f"alpha_diversity has no columns: {alpha_path}")

    first_column = columns[0]
    if first_column != "SampleID":
        lower_map = {column.lower(): column for column in columns}
        first_column = lower_map.get("sampleid", first_column)
    table = table.rename(columns={first_column: "SampleID"}).copy()
    table["SampleID"] = table["SampleID"].astype(str).str.strip()

    lower_to_column = {
        str(column).strip().lower(): column
        for column in table.columns
    }
    rename_map: dict[str, str] = {}
    for metric, aliases in ALPHA_METRIC_ALIASES.items():
        matched = next(
            (
                lower_to_column[str(alias).strip().lower()]
                for alias in aliases
                if str(alias).strip().lower() in lower_to_column
            ),
            None,
        )
        if matched is not None:
            rename_map[matched] = metric

    table = table.rename(columns=rename_map).copy()
    if "invsimpson" not in table.columns and "simpson" in table.columns:
        simpson = pd.to_numeric(table["simpson"], errors="raise")
        dominance = 1.0 - simpson
        table["invsimpson"] = np.where(dominance > 0, 1.0 / dominance, 0.0)

    missing_metrics = [
        metric for metric in DEFAULT_ALPHA_METRICS
        if metric not in table.columns
    ]
    if missing_metrics:
        raise ValueError(
            "alpha_diversity is missing required metrics: "
            f"{missing_metrics}"
        )

    normalized = table.loc[:, ["SampleID", *DEFAULT_ALPHA_METRICS]].copy()
    if normalized["SampleID"].duplicated().any():
        duplicates = normalized.loc[normalized["SampleID"].duplicated(), "SampleID"].tolist()
        raise ValueError(f"alpha_diversity contains duplicate SampleID values: {duplicates[:8]}")

    for metric in DEFAULT_ALPHA_METRICS:
        normalized[metric] = pd.to_numeric(normalized[metric], errors="raise")
    return normalized


def resolve_alpha_metrics(metrics: Sequence[str] | None = None) -> list[str]:
    """Resolve alpha metric names with aliases."""

    if metrics is None:
        return list(DEFAULT_ALPHA_METRICS)
    resolved: list[str] = []
    alias_to_metric = {
        alias.lower(): metric
        for metric, aliases in ALPHA_METRIC_ALIASES.items()
        for alias in aliases
    }
    for metric in metrics:
        canonical = alias_to_metric.get(str(metric).strip().lower())
        if canonical is None:
            raise ValueError(
                "Unknown alpha metric "
                f"'{metric}'. Expected one of: {list(DEFAULT_ALPHA_METRICS)}"
            )
        if canonical not in resolved:
            resolved.append(canonical)
    if not resolved:
        raise ValueError("metrics must not be empty.")
    return resolved


def read_distance_matrix(path: str, label: str | None = None) -> pd.DataFrame:
    """Read and validate a sample-by-sample beta distance matrix."""

    resolved_path = ensure_file(path, label or "distance_matrix")
    table = read_table(resolved_path, label or os.path.basename(resolved_path), index_col=0)
    if table.empty:
        raise ValueError(f"Distance matrix is empty: {resolved_path}")

    table.index = table.index.astype(str).str.strip()
    table.columns = [str(column).strip() for column in table.columns]
    if table.index.has_duplicates:
        raise ValueError(f"Distance matrix contains duplicate sample IDs: {resolved_path}")
    if table.shape[0] != table.shape[1]:
        raise ValueError(f"Distance matrix is not square: {resolved_path}")

    missing_columns = [sample_id for sample_id in table.index if sample_id not in table.columns]
    if missing_columns:
        raise ValueError(
            f"Distance matrix columns do not match rows in {resolved_path}: "
            f"{missing_columns[:8]}"
        )

    matrix = table.loc[table.index, table.index].apply(pd.to_numeric, errors="coerce")
    if matrix.isna().to_numpy().any():
        matrix = matrix.combine_first(matrix.T).fillna(0.0)

    values = matrix.to_numpy(dtype=float, copy=True)
    if not np.allclose(values, values.T, atol=1e-8):
        values = (values + values.T) / 2.0
    np.fill_diagonal(values, 0.0)

    return pd.DataFrame(values, index=matrix.index.tolist(), columns=matrix.columns.tolist())


def find_beta_distance_files(beta_dir: str, metrics: Sequence[str] | None = None) -> dict[str, str]:
    """Find beta distance matrix files in a directory."""

    resolved_beta_dir = os.path.abspath(beta_dir)
    if not os.path.isdir(resolved_beta_dir):
        raise FileNotFoundError(f"beta_dir not found: {resolved_beta_dir}")

    requested_metrics = [str(metric).strip().lower() for metric in (metrics or DEFAULT_BETA_METRICS)]
    file_map: dict[str, str] = {}
    for metric in requested_metrics:
        for suffix in (".tsv", ".txt", ".csv"):
            candidate = os.path.join(resolved_beta_dir, f"{metric}{suffix}")
            if os.path.isfile(candidate):
                file_map[metric] = os.path.abspath(candidate)
                break
    if not file_map:
        raise FileNotFoundError(f"No beta distance matrices found in: {resolved_beta_dir}")
    return file_map


def normalize_metric_title(metric: str) -> str:
    """Return a display title for a beta metric."""

    display = {
        "braycurtis": "Bray-Curtis",
        "euclidean": "Euclidean",
        "jaccard": "Jaccard",
        "manhattan": "Manhattan",
        "unweighted_unifrac": "Unweighted UniFrac",
        "weighted_unifrac": "Weighted UniFrac",
    }
    return display.get(metric, str(metric).replace("_", " ").title())


def find_taxonomy_files(
    taxonomy_summary_dir: str,
    levels: Sequence[str] | None = None,
) -> dict[str, str]:
    """Find taxonomy summary files for requested levels."""

    resolved_dir = os.path.abspath(taxonomy_summary_dir)
    if not os.path.isdir(resolved_dir):
        raise FileNotFoundError(f"taxonomy_summary_dir not found: {resolved_dir}")

    requested_levels = [str(level).strip().lower() for level in (levels or DEFAULT_TAXONOMY_LEVELS)]
    file_map: dict[str, str] = {}
    for level in requested_levels:
        candidate = os.path.join(resolved_dir, f"{level}.tsv")
        if os.path.isfile(candidate):
            file_map[level] = os.path.abspath(candidate)
    if not file_map:
        raise FileNotFoundError(f"No taxonomy summary files found in: {resolved_dir}")
    return file_map


def read_taxonomy_summary(path: str, level: str) -> pd.DataFrame:
    """Read a taxonomy summary table and return taxon plus sample columns."""

    table = read_table(path, f"{level}_taxonomy_summary")
    first_column = table.columns[0]
    table = table.rename(columns={first_column: "Taxon"}).copy()
    table["Taxon"] = table["Taxon"].astype(str).str.strip().replace("", "(Unassigned)")

    value_columns = [
        column for column in table.columns
        if column != "Taxon" and str(column).strip().lower() not in SUMMARY_COLUMNS
    ]
    if not value_columns:
        raise ValueError(f"{level} taxonomy summary has no sample columns: {path}")

    for column in value_columns:
        table[column] = pd.to_numeric(table[column], errors="coerce").fillna(0.0)
    return table.loc[:, ["Taxon", *value_columns]].copy()


def sort_sample_ids(sample_ids: Iterable[str]) -> list[str]:
    """Sort samples by inferred group and trailing replicate number."""

    def _key(sample_id: str) -> tuple[str, int, str]:
        text = str(sample_id)
        group = infer_group(text)
        match = re.match(r"^(.+?)(\d+)$", text)
        number = int(match.group(2)) if match else 0
        return group, number, text

    return sorted([str(sample_id) for sample_id in sample_ids], key=_key)


def plotly_palette() -> list[str]:
    """Return a long qualitative color palette."""

    import plotly.express as px

    return (
        px.colors.qualitative.Dark24
        + px.colors.qualitative.Light24
        + px.colors.qualitative.Set3
        + px.colors.qualitative.Pastel
        + px.colors.qualitative.Bold
    )
