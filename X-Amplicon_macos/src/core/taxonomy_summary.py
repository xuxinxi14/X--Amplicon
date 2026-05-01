"""Taxonomy parsing and abundance summarization utilities."""

from __future__ import annotations

import os
import re

import pandas as pd

UNASSIGNED_LABEL = "Unassigned"
SUMMARY_UNASSIGNED_LABEL = "(Unassigned)"
TAXONOMY_COLUMNS = [
    "OTUID",
    "Kingdom",
    "Phylum",
    "Class",
    "Order",
    "Family",
    "Genus",
    "Species",
]
RANK_CODE_TO_COLUMN = {
    "d": "Kingdom",
    "k": "Kingdom",
    "p": "Phylum",
    "c": "Class",
    "o": "Order",
    "f": "Family",
    "g": "Genus",
    "s": "Species",
}
SINTAX_TOKEN_PATTERN = re.compile(
    r"^\s*([dkpcofgs])\s*:\s*(.*?)\s*(?:\(([^()]*)\))?\s*$",
    re.IGNORECASE,
)


def _validate_otutab(otutab: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(otutab, pd.DataFrame):
        raise TypeError("otutab must be a pandas DataFrame.")

    if otutab.empty:
        raise ValueError("otutab must not be empty.")

    if otutab.index.has_duplicates:
        raise ValueError("otutab index contains duplicate OTU IDs.")

    if otutab.columns.has_duplicates:
        raise ValueError("otutab columns contain duplicate sample IDs.")

    try:
        counts = otutab.apply(pd.to_numeric, errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError("otutab must contain only numeric abundance values.") from exc

    if counts.isna().to_numpy().any():
        raise ValueError("otutab must not contain missing values.")

    if (counts < 0).to_numpy().any():
        raise ValueError("otutab must not contain negative values.")

    return counts


def _select_taxonomy_field(parts: list[str]) -> str:
    if len(parts) >= 4 and parts[3].strip():
        return parts[3].strip()
    if len(parts) >= 2 and parts[1].strip():
        return parts[1].strip()
    return ""


def _parse_taxonomy_field(taxonomy_field: str) -> dict[str, str]:
    parsed = {column: UNASSIGNED_LABEL for column in TAXONOMY_COLUMNS[1:]}
    if not taxonomy_field:
        return parsed

    normalized_field = taxonomy_field.strip()
    if normalized_field.lower().startswith("tax="):
        normalized_field = normalized_field[4:]

    for token in normalized_field.split(","):
        stripped_token = token.strip()
        if not stripped_token:
            continue

        match = SINTAX_TOKEN_PATTERN.match(stripped_token)
        if match is None:
            continue

        rank_code, taxon_name, _confidence = match.groups()
        column_name = RANK_CODE_TO_COLUMN.get(rank_code.lower())
        if column_name is None:
            continue

        cleaned_taxon_name = taxon_name.strip().strip('"').strip("'")
        if cleaned_taxon_name:
            parsed[column_name] = cleaned_taxon_name

    return parsed


def parse_sintax_to_dataframe(sintax_path: str) -> pd.DataFrame:
    """Parse a sintax annotation file into a standardized taxonomy table.

    Args:
        sintax_path: Path to an `otus.sintax`-style file.

    Returns:
        A DataFrame with columns `OTUID`, `Kingdom`, `Phylum`, `Class`,
        `Order`, `Family`, `Genus`, and `Species`. Missing ranks are filled
        with `Unassigned`.
    """

    if not isinstance(sintax_path, str):
        raise TypeError("sintax_path must be a string.")

    resolved_path = os.path.abspath(sintax_path)
    if not os.path.isfile(resolved_path):
        raise FileNotFoundError(f"sintax file not found: {resolved_path}")

    records: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    with open(resolved_path, "r", encoding="utf-8", newline=None) as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\r\n")
            if not line:
                continue

            parts = line.split("\t")
            otuid = parts[0].strip()
            if not otuid:
                raise ValueError("sintax file contains a row with an empty OTU ID.")
            if otuid in seen_ids:
                raise ValueError(f"sintax file contains duplicate OTU IDs: {otuid}")

            seen_ids.add(otuid)
            taxonomy_field = _select_taxonomy_field(parts)
            parsed_taxonomy = _parse_taxonomy_field(taxonomy_field)
            records.append({"OTUID": otuid, **parsed_taxonomy})

    if not records:
        raise ValueError("sintax file must not be empty.")

    return pd.DataFrame.from_records(records, columns=TAXONOMY_COLUMNS)


def _validate_taxonomy(taxonomy: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(taxonomy, pd.DataFrame):
        raise TypeError("taxonomy must be a pandas DataFrame.")

    if taxonomy.empty:
        raise ValueError("taxonomy must not be empty.")

    if "OTUID" in taxonomy.columns:
        if taxonomy["OTUID"].duplicated().any():
            raise ValueError("taxonomy contains duplicate OTUID values.")
        aligned_taxonomy = taxonomy.set_index("OTUID", drop=False)
    else:
        if taxonomy.index.has_duplicates:
            raise ValueError("taxonomy index contains duplicate OTU IDs.")
        aligned_taxonomy = taxonomy.copy()
        aligned_taxonomy.insert(0, "OTUID", taxonomy.index.astype(str))
        aligned_taxonomy.index = taxonomy.index.astype(str)

    missing_columns = [column for column in TAXONOMY_COLUMNS if column not in aligned_taxonomy.columns]
    if missing_columns:
        raise ValueError(
            "taxonomy is missing required columns: "
            f"{missing_columns}"
        )

    cleaned_taxonomy = aligned_taxonomy.loc[:, TAXONOMY_COLUMNS].copy()
    cleaned_taxonomy.index = cleaned_taxonomy["OTUID"].astype(str)
    for column in TAXONOMY_COLUMNS[1:]:
        cleaned_taxonomy[column] = (
            cleaned_taxonomy[column]
            .fillna(UNASSIGNED_LABEL)
            .astype(str)
            .str.strip()
            .replace("", UNASSIGNED_LABEL)
        )

    return cleaned_taxonomy


def summarize_taxa_abundance(
    otutab: pd.DataFrame,
    taxonomy: pd.DataFrame,
    rank: str,
) -> pd.DataFrame:
    """Summarize OTU abundance by a selected taxonomy rank.

    Args:
        otutab: OTU table with OTU IDs as rows and sample IDs as columns.
        taxonomy: Taxonomy table containing at least `OTUID` plus the standard
            rank columns produced by `parse_sintax_to_dataframe`.
        rank: Taxonomy rank to summarize, such as `Phylum` or `Genus`.

    Returns:
        A DataFrame indexed by the selected taxonomy rank with sample-relative
        abundance percentages in each sample column and an `All` column giving
        the percentage of OTUs assigned to each taxonomy label in the taxonomy
        table.
    """

    counts = _validate_otutab(otutab)
    cleaned_taxonomy = _validate_taxonomy(taxonomy)

    if not isinstance(rank, str):
        raise TypeError("rank must be a string.")

    resolved_rank = rank.strip()
    if resolved_rank not in TAXONOMY_COLUMNS[1:]:
        raise ValueError(
            "rank must be one of: Kingdom, Phylum, Class, Order, Family, "
            "Genus, Species."
        )

    otu_ids = [str(otu_id) for otu_id in counts.index]
    if len(otu_ids) != len(set(otu_ids)):
        raise ValueError("otutab OTU IDs must remain unique after string conversion.")

    missing_otu_ids = [otu_id for otu_id in otu_ids if otu_id not in cleaned_taxonomy.index]
    if missing_otu_ids:
        raise ValueError(
            "taxonomy is missing OTU IDs required by otutab: "
            f"{missing_otu_ids[:10]}"
        )

    aligned_counts = counts.copy()
    aligned_counts.index = otu_ids
    relative_abundance = aligned_counts.div(aligned_counts.sum(axis=0), axis=1) * 100.0

    taxonomy_labels = cleaned_taxonomy[resolved_rank].copy()
    taxonomy_labels = taxonomy_labels.replace(UNASSIGNED_LABEL, SUMMARY_UNASSIGNED_LABEL)

    sample_group_labels = taxonomy_labels.loc[otu_ids]
    sample_summary = relative_abundance.groupby(sample_group_labels, sort=False).sum()

    all_summary = (taxonomy_labels.value_counts(sort=False) / len(taxonomy_labels)) * 100.0
    taxon_order = list(all_summary.sort_values(ascending=False, kind="stable").index)

    sample_summary = sample_summary.reindex(taxon_order, fill_value=0.0)
    sample_summary["All"] = all_summary.reindex(taxon_order).to_numpy(dtype=float)
    sample_summary.index.name = resolved_rank
    return sample_summary
