"""Feature table filtering workflow for 16S, ITS, or no-filter routes."""

from __future__ import annotations

import os
import re
import shutil
from typing import Any, Dict, Optional

from .workflow_common import (
    ensure_input_file,
    ensure_input_fasta,
)

ROUTE_16S = "16s"
ROUTE_ITS = "its"
ROUTE_NONE = "none"
VALID_ROUTES = {ROUTE_16S, ROUTE_ITS, ROUTE_NONE}
BACTERIA_ARCHAEA_PATTERN = re.compile(r"Bacteria|Archaea")
FUNGI_PATTERN = re.compile(r"Fungi")
CHLOROPLAST_PATTERN = re.compile(r"Chloroplast")
MITOCHONDRIA_PATTERN = re.compile(r"Mitochondria")


def _resolve_route(route: str) -> str:
    normalized = str(route).strip().lower()
    if normalized not in VALID_ROUTES:
        raise ValueError("route must be one of: 16s, its, none.")
    return normalized


def _read_otutab(path: str) -> tuple[list[str], list[tuple[str, list[int]]]]:
    with open(path, "r", encoding="utf-8", newline=None) as handle:
        header_line = handle.readline().rstrip("\r\n")
        if not header_line:
            raise ValueError(f"Feature table is empty: {path}")

        header_parts = header_line.split("\t")
        if len(header_parts) < 2:
            raise ValueError(f"Invalid feature table header: {path}")

        sample_names = header_parts[1:]
        rows: list[tuple[str, list[int]]] = []

        for raw_line in handle:
            line = raw_line.rstrip("\r\n")
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) != len(sample_names) + 1:
                raise ValueError(f"Invalid feature table row: {line}")

            feature_id = parts[0]
            counts = [int(value) for value in parts[1:]]
            rows.append((feature_id, counts))

    return sample_names, rows


def _read_sintax(path: str) -> tuple[list[str], Dict[str, list[str]], Dict[str, str]]:
    order: list[str] = []
    columns_by_id: Dict[str, list[str]] = {}
    line_by_id: Dict[str, str] = {}

    with open(path, "r", encoding="utf-8", newline=None) as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\r\n")
            if not line:
                continue

            parts = line.split("\t")
            while len(parts) < 4:
                parts.append("")

            feature_id = parts[0]
            order.append(feature_id)
            columns_by_id[feature_id] = parts
            line_by_id[feature_id] = line

    return order, columns_by_id, line_by_id


def _sum_selected_counts(
    rows: list[tuple[str, list[int]]],
    selected_ids: set[str],
    sample_count: int,
) -> list[int]:
    totals = [0] * sample_count
    for feature_id, counts in rows:
        if feature_id in selected_ids:
            for index, value in enumerate(counts):
                totals[index] += value
    return totals


def _write_stat_file(
    path: str,
    sample_names: list[str],
    total_reads: list[int],
    nonspecific_reads: list[int],
    chloroplast_reads: list[int],
    mitochondria_reads: list[int],
    filtered_reads: list[int],
) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            "SampleID\t"
            "total_reads\tnonspecific_reads\tchloroplast_reads\t"
            "mitochondria_reads\tfiltered_reads\n"
        )
        for index, sample_name in enumerate(sample_names):
            handle.write(
                f"{sample_name}\t{total_reads[index]}\t{nonspecific_reads[index]}\t"
                f"{chloroplast_reads[index]}\t{mitochondria_reads[index]}\t"
                f"{filtered_reads[index]}\n"
            )


def _write_otutab(
    path: str,
    sample_names: list[str],
    rows: list[tuple[str, list[int]]],
) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("#OTUID\t" + "\t".join(sample_names) + "\n")
        for feature_id, counts in rows:
            handle.write(
                feature_id + "\t" + "\t".join(str(value) for value in counts) + "\n"
            )


def _write_id_file(path: str, feature_ids: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for feature_id in feature_ids:
            handle.write(f"{feature_id}\n")


def _write_sintax_subset(
    path: str,
    feature_ids: list[str],
    sintax_line_by_id: Dict[str, str],
) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for feature_id in feature_ids:
            if feature_id not in sintax_line_by_id:
                raise ValueError(f"Feature ID missing from taxonomy file: {feature_id}")
            handle.write(sintax_line_by_id[feature_id] + "\n")


def _read_fasta_records(path: str) -> Dict[str, str]:
    records: Dict[str, str] = {}
    current_id: Optional[str] = None
    current_lines: list[str] = []

    with open(path, "r", encoding="utf-8", newline=None) as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\r\n")
            if not line:
                continue
            if line.startswith(">"):
                if current_id is not None:
                    records[current_id] = "\n".join(current_lines)
                current_id = line[1:].split(None, 1)[0]
                if not current_id:
                    raise ValueError(f"FASTA record with empty ID in: {path}")
                current_lines = [line]
            else:
                if current_id is None:
                    raise ValueError(f"FASTA sequence found before first header in: {path}")
                current_lines.append(line)

    if current_id is not None:
        records[current_id] = "\n".join(current_lines)

    return records


def _write_fasta_subset(
    source_path: str,
    destination_path: str,
    feature_ids: list[str],
) -> None:
    records_by_id = _read_fasta_records(source_path)
    missing_ids = [feature_id for feature_id in feature_ids if feature_id not in records_by_id]
    if missing_ids:
        preview = ", ".join(missing_ids[:10])
        suffix = "" if len(missing_ids) <= 10 else f", ... ({len(missing_ids)} total)"
        raise ValueError(f"Feature IDs missing from representative FASTA: {preview}{suffix}")

    with open(destination_path, "w", encoding="utf-8", newline="\n") as handle:
        for feature_id in feature_ids:
            handle.write(records_by_id[feature_id])
            handle.write("\n")


def _copy_if_needed(source: str, destination: str) -> None:
    if os.path.abspath(source) == os.path.abspath(destination):
        return
    shutil.copyfile(source, destination)


def run_otutab_filter(
    input_table: str,
    taxonomy_path: str,
    representative_fasta: str,
    output_dir: str,
    route: str,
    usearch_path: Optional[str] = None,
    output_table_path: Optional[str] = None,
    output_fasta_path: Optional[str] = None,
    output_taxonomy_path: Optional[str] = None,
    output_stat_path: Optional[str] = None,
    discard_path: Optional[str] = None,
    output_id_path: Optional[str] = None,
    command_timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Filter feature tables by taxonomy and extract matching representatives."""

    resolved_route = _resolve_route(route)
    resolved_input_table = ensure_input_file(input_table, "input_table")
    resolved_taxonomy_path = ensure_input_file(taxonomy_path, "taxonomy_path")
    resolved_representative_fasta = ensure_input_fasta(representative_fasta)
    resolved_output_dir = os.path.abspath(output_dir)
    os.makedirs(resolved_output_dir, exist_ok=True)

    resolved_output_table_path = os.path.abspath(
        output_table_path or os.path.join(resolved_output_dir, "otutab.txt")
    )
    resolved_output_fasta_path = os.path.abspath(
        output_fasta_path or os.path.join(resolved_output_dir, "otus.fa")
    )
    resolved_output_taxonomy_path = os.path.abspath(
        output_taxonomy_path or os.path.join(resolved_output_dir, "otus.sintax")
    )
    resolved_output_id_path = os.path.abspath(
        output_id_path or os.path.join(resolved_output_dir, "otutab.id")
    )

    if resolved_route == ROUTE_16S:
        default_stat_name = "otutab_nonBac.stat"
    elif resolved_route == ROUTE_ITS:
        default_stat_name = "otutab_nonFungi.stat"
    else:
        default_stat_name = None

    resolved_output_stat_path = (
        None
        if default_stat_name is None and output_stat_path is None
        else os.path.abspath(
            output_stat_path or os.path.join(resolved_output_dir, default_stat_name)
        )
    )
    resolved_discard_path = (
        None
        if resolved_route == ROUTE_NONE and discard_path is None
        else os.path.abspath(
            discard_path or os.path.join(resolved_output_dir, "otus.sintax.discard")
        )
    )

    for target_path in [
        resolved_output_table_path,
        resolved_output_fasta_path,
        resolved_output_taxonomy_path,
        resolved_output_id_path,
        resolved_output_stat_path,
        resolved_discard_path,
    ]:
        if target_path is None:
            continue
        parent_dir = os.path.dirname(target_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

    print("[OTUTAB FILTER] Starting taxonomy-based feature filtering workflow.")
    print(f"[OTUTAB FILTER] Input feature table: {resolved_input_table}")
    print(f"[OTUTAB FILTER] Input taxonomy: {resolved_taxonomy_path}")
    print(f"[OTUTAB FILTER] Input representative FASTA: {resolved_representative_fasta}")
    print(f"[OTUTAB FILTER] Output directory: {resolved_output_dir}")
    print(f"[OTUTAB FILTER] Route: {resolved_route}")

    if resolved_route == ROUTE_NONE:
        print("[OTUTAB FILTER] Route is none. Copying files without filtering.")
        _copy_if_needed(resolved_input_table, resolved_output_table_path)
        _copy_if_needed(resolved_representative_fasta, resolved_output_fasta_path)
        _copy_if_needed(resolved_taxonomy_path, resolved_output_taxonomy_path)
        print("[OTUTAB FILTER] Workflow finished successfully.")
        return {
            "route": resolved_route,
            "feature_table": resolved_output_table_path,
            "representative_fasta": resolved_output_fasta_path,
            "taxonomy": resolved_output_taxonomy_path,
            "stat": None,
            "discard": None,
            "selected_ids": None,
            "kept_features": None,
            "discarded_features": None,
        }

    sample_names, otutab_rows = _read_otutab(resolved_input_table)
    sintax_order, sintax_columns_by_id, sintax_line_by_id = _read_sintax(
        resolved_taxonomy_path
    )

    total_reads = _sum_selected_counts(
        otutab_rows,
        {feature_id for feature_id, _ in otutab_rows},
        len(sample_names),
    )

    if resolved_route == ROUTE_16S:
        keep_pattern = BACTERIA_ARCHAEA_PATTERN
    else:
        keep_pattern = FUNGI_PATTERN

    nonspecific_ids: list[str] = []
    chloroplast_ids: list[str] = []
    mitochondria_ids: list[str] = []
    discard_lines: list[str] = []
    remaining_ids: list[str] = []

    for feature_id in sintax_order:
        columns = sintax_columns_by_id[feature_id]
        if keep_pattern.search(columns[3]):
            remaining_ids.append(feature_id)
        else:
            nonspecific_ids.append(feature_id)
            discard_lines.append(sintax_line_by_id[feature_id])

    after_nonspecific_ids: list[str] = []
    for feature_id in remaining_ids:
        columns = sintax_columns_by_id[feature_id]
        if CHLOROPLAST_PATTERN.search(columns[1]):
            chloroplast_ids.append(feature_id)
            discard_lines.append(sintax_line_by_id[feature_id])
        else:
            after_nonspecific_ids.append(feature_id)

    kept_taxonomy_ids: list[str] = []
    for feature_id in after_nonspecific_ids:
        columns = sintax_columns_by_id[feature_id]
        if MITOCHONDRIA_PATTERN.search(columns[1]):
            mitochondria_ids.append(feature_id)
            discard_lines.append(sintax_line_by_id[feature_id])
        else:
            kept_taxonomy_ids.append(feature_id)

    kept_taxonomy_id_set = set(kept_taxonomy_ids)
    filtered_rows = [
        (feature_id, counts)
        for feature_id, counts in otutab_rows
        if feature_id in kept_taxonomy_id_set
    ]
    filtered_rows.sort(key=lambda item: sum(item[1]), reverse=True)
    selected_feature_ids = [feature_id for feature_id, _ in filtered_rows]

    nonspecific_reads = _sum_selected_counts(
        otutab_rows, set(nonspecific_ids), len(sample_names)
    )
    chloroplast_reads = _sum_selected_counts(
        otutab_rows, set(chloroplast_ids), len(sample_names)
    )
    mitochondria_reads = _sum_selected_counts(
        otutab_rows, set(mitochondria_ids), len(sample_names)
    )
    filtered_reads = _sum_selected_counts(
        otutab_rows, set(selected_feature_ids), len(sample_names)
    )

    if resolved_discard_path is not None:
        with open(resolved_discard_path, "w", encoding="utf-8", newline="\n") as handle:
            for line in discard_lines:
                handle.write(line + "\n")

    if resolved_output_stat_path is not None:
        _write_stat_file(
            resolved_output_stat_path,
            sample_names,
            total_reads,
            nonspecific_reads,
            chloroplast_reads,
            mitochondria_reads,
            filtered_reads,
        )

    _write_otutab(resolved_output_table_path, sample_names, filtered_rows)
    _write_id_file(resolved_output_id_path, selected_feature_ids)

    print("[OTUTAB FILTER] Extracting representative sequences with Python FASTA subset.")
    _write_fasta_subset(
        resolved_representative_fasta,
        resolved_output_fasta_path,
        selected_feature_ids,
    )

    _write_sintax_subset(
        resolved_output_taxonomy_path,
        selected_feature_ids,
        sintax_line_by_id,
    )

    print("[OTUTAB FILTER] Workflow finished successfully.")

    return {
        "route": resolved_route,
        "feature_table": resolved_output_table_path,
        "representative_fasta": resolved_output_fasta_path,
        "taxonomy": resolved_output_taxonomy_path,
        "stat": resolved_output_stat_path,
        "discard": resolved_discard_path,
        "selected_ids": resolved_output_id_path,
        "kept_features": len(selected_feature_ids),
        "discarded_features": len(discard_lines),
        "usearch": None,
        "command_timeout": command_timeout,
    }
