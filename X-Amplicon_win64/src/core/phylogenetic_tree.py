"""Generate rooted OTU/ASV trees for phylogenetic beta diversity."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal, Sequence

import numpy as np
from scipy.cluster.hierarchy import ClusterNode, linkage as scipy_linkage, to_tree
from scipy.spatial.distance import pdist

from .workflow_common import ensure_input_fasta

LinkageMethod = Literal["max", "min", "avg"]
DistanceMethod = Literal["p_distance", "edit"]

MIN_BRANCH_LENGTH = 1e-9
VALID_LINKAGE_METHODS = {"max", "min", "avg"}
VALID_DISTANCE_METHODS = {"p_distance", "edit"}
SCIPY_LINKAGE_BY_METHOD = {
    "max": "complete",
    "min": "single",
    "avg": "average",
}
GAP_BYTE = ord("-")


@dataclass(frozen=True)
class FastaRecord:
    """FASTA record used for tree construction."""

    record_id: str
    sequence: str


def _normalize_record_id(header: str) -> str:
    token = header.strip().split()[0] if header.strip() else ""
    token = token.split(";", 1)[0].strip()
    if not token:
        raise ValueError("FASTA header contains an empty record ID.")
    return token


def read_fasta_records(path: str) -> list[FastaRecord]:
    """Read FASTA records, using the first header token as the feature ID."""

    resolved_path = ensure_input_fasta(path)
    records: list[FastaRecord] = []
    current_id: str | None = None
    sequence_parts: list[str] = []
    seen_ids: set[str] = set()

    with open(resolved_path, "r", encoding="utf-8", newline=None) as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current_id is not None:
                    sequence = "".join(sequence_parts).upper().replace("U", "T")
                    if not sequence:
                        raise ValueError(f"FASTA record has an empty sequence: {current_id}")
                    records.append(FastaRecord(current_id, sequence))

                current_id = _normalize_record_id(line[1:])
                if current_id in seen_ids:
                    raise ValueError(f"FASTA contains duplicate record ID: {current_id}")
                seen_ids.add(current_id)
                sequence_parts = []
            else:
                if current_id is None:
                    raise ValueError("FASTA sequence encountered before the first header.")
                sequence_parts.append(line)

    if current_id is not None:
        sequence = "".join(sequence_parts).upper().replace("U", "T")
        if not sequence:
            raise ValueError(f"FASTA record has an empty sequence: {current_id}")
        records.append(FastaRecord(current_id, sequence))

    if not records:
        raise ValueError(f"FASTA contains no records: {resolved_path}")
    return records


def _records_to_padded_ascii_matrix(records: Sequence[FastaRecord]) -> np.ndarray:
    max_length = max(len(record.sequence) for record in records)
    matrix = np.full((len(records), max_length), GAP_BYTE, dtype=np.uint8)
    for row_index, record in enumerate(records):
        sequence_bytes = record.sequence.encode("ascii", errors="replace")
        matrix[row_index, : len(sequence_bytes)] = np.frombuffer(
            sequence_bytes,
            dtype=np.uint8,
        )
    return matrix


def _build_condensed_distance_vector(records: Sequence[FastaRecord]) -> np.ndarray:
    if len(records) < 2:
        return np.array([], dtype=np.float64)
    return pdist(_records_to_padded_ascii_matrix(records), metric="hamming")


def build_agglomerative_tree(
    records: Sequence[FastaRecord],
    *,
    linkage: LinkageMethod = "max",
) -> ClusterNode:
    """Build a rooted agglomerative tree from representative sequences."""

    if linkage not in VALID_LINKAGE_METHODS:
        raise ValueError("linkage must be one of: max, min, avg.")
    if not records:
        raise ValueError("At least one FASTA record is required to build a tree.")

    if len(records) == 1:
        return ClusterNode(0)

    linkage_matrix = scipy_linkage(
        _build_condensed_distance_vector(records),
        method=SCIPY_LINKAGE_BY_METHOD[linkage],
    )
    return to_tree(linkage_matrix, rd=False)


def _quote_newick_label(label: str) -> str:
    return "'" + label.replace("'", "''") + "'"


def _format_branch_length(length: float) -> str:
    return f"{max(float(length), MIN_BRANCH_LENGTH):.12g}"


def _node_height(node: ClusterNode) -> float:
    if node.is_leaf():
        return 0.0
    return float(node.dist) / 2.0


def _to_newick(
    node: ClusterNode,
    record_ids: Sequence[str],
    parent_height: float | None = None,
) -> str:
    node_height = _node_height(node)
    if node.is_leaf():
        rendered = _quote_newick_label(record_ids[node.id])
    else:
        if node.left is None or node.right is None:
            raise ValueError("Internal tree node must have two children.")
        rendered = (
            f"({_to_newick(node.left, record_ids, node_height)},"
            f"{_to_newick(node.right, record_ids, node_height)})"
        )

    if parent_height is None:
        return rendered
    return f"{rendered}:{_format_branch_length(parent_height - node_height)}"


def write_newick_tree(
    root: ClusterNode,
    output_tree_path: str,
    record_ids: Sequence[str],
) -> str:
    """Write a rooted Newick tree and return its absolute path."""

    resolved_output_path = os.path.abspath(output_tree_path)
    os.makedirs(os.path.dirname(resolved_output_path), exist_ok=True)

    if root.is_leaf():
        tree_text = f"({_quote_newick_label(record_ids[root.id])}:{_format_branch_length(1.0)})root;\n"
    else:
        tree_text = f"{_to_newick(root, record_ids)}root;\n"

    with open(resolved_output_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(tree_text)
    return resolved_output_path


def run_phylogenetic_tree_generation(
    input_fasta: str,
    output_tree_path: str,
    *,
    linkage: LinkageMethod = "max",
    distance_method: DistanceMethod = "p_distance",
) -> dict[str, Any]:
    """Generate a rooted Newick tree from representative OTU/ASV sequences."""

    if distance_method not in VALID_DISTANCE_METHODS:
        raise ValueError("distance_method must be one of: p_distance.")

    records = read_fasta_records(input_fasta)
    root = build_agglomerative_tree(records, linkage=linkage)
    resolved_output_path = write_newick_tree(
        root,
        output_tree_path,
        [record.record_id for record in records],
    )

    return {
        "input_fasta": os.path.abspath(input_fasta),
        "tree_path": resolved_output_path,
        "record_count": len(records),
        "linkage": linkage,
        "distance_method": "p_distance",
        "format": "newick",
    }
