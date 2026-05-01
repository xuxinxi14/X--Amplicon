"""FASTQ pair preview for Web UI project setup."""

from __future__ import annotations

from pathlib import Path

from webui.backend.config import resolve_path
from webui.backend.models.project import FastqPairingPreview, FastqPairRecord
from webui.backend.services.metadata_validator import sample_ids_from_metadata

FASTQ_SUFFIXES = (".fq", ".fastq", ".fq.gz", ".fastq.gz")


def _is_fastq_name(name: str) -> bool:
    lowered = name.lower()
    return any(lowered.endswith(suffix) for suffix in FASTQ_SUFFIXES)


def preview_fastq_pairs(
    metadata_path: str,
    seq_dir: str,
    *,
    sample_id_col: str = "SampleID",
    read1_suffix: str = "_1.fq.gz",
    read2_suffix: str = "_2.fq.gz",
    base_dir: str | Path | None = None,
) -> FastqPairingPreview:
    """Preview FASTQ R1/R2 matching by sample ID and suffix."""

    resolved_metadata = resolve_path(metadata_path, base_dir)
    resolved_seq_dir = resolve_path(seq_dir, base_dir)
    result = FastqPairingPreview(
        status="failed",
        metadata_path=str(resolved_metadata),
        seq_dir=str(resolved_seq_dir),
        read1_suffix=read1_suffix,
        read2_suffix=read2_suffix,
    )

    if not resolved_metadata.is_file():
        result.messages.append(f"Metadata file was not found: {resolved_metadata}")
        result.suggestions.append("Select a metadata table before previewing FASTQ pairs.")
        return result
    if not resolved_seq_dir.is_dir():
        result.messages.append(f"FASTQ directory was not found: {resolved_seq_dir}")
        result.suggestions.append("Select the folder that contains paired-end FASTQ files.")
        return result

    try:
        _, sample_ids = sample_ids_from_metadata(str(resolved_metadata), sample_id_col=sample_id_col)
    except Exception as exc:
        result.messages.append(f"Sample IDs could not be read from metadata: {exc}")
        result.suggestions.append("Validate metadata before previewing FASTQ pairs.")
        return result

    result.sample_count = len(sample_ids)
    if not sample_ids:
        result.messages.append("Metadata does not contain any non-empty sample IDs.")
        return result

    file_names = {entry.name for entry in resolved_seq_dir.iterdir() if entry.is_file()}
    expected_names: set[str] = set()

    for sample_id in sample_ids:
        read1_name = f"{sample_id}{read1_suffix}"
        read2_name = f"{sample_id}{read2_suffix}"
        expected_names.update({read1_name, read2_name})
        read1_path = resolved_seq_dir / read1_name
        read2_path = resolved_seq_dir / read2_name
        read1_exists = read1_name in file_names
        read2_exists = read2_name in file_names
        if read1_exists and read2_exists:
            status = "ok"
            result.matched_pairs += 1
        elif read1_exists:
            status = "missing_r2"
            result.missing_read2.append(str(read2_path))
        elif read2_exists:
            status = "missing_r1"
            result.missing_read1.append(str(read1_path))
        else:
            status = "missing_both"
            result.missing_read1.append(str(read1_path))
            result.missing_read2.append(str(read2_path))
        result.pairs.append(
            FastqPairRecord(
                sample_id=sample_id,
                read1_path=str(read1_path),
                read2_path=str(read2_path),
                read1_exists=read1_exists,
                read2_exists=read2_exists,
                status=status,
            )
        )

    result.extra_fastq_files = sorted(
        str(resolved_seq_dir / name)
        for name in file_names
        if _is_fastq_name(name) and name not in expected_names
    )

    if result.missing_read1 or result.missing_read2:
        result.status = "failed"
        result.messages.append(
            f"Matched {result.matched_pairs} of {result.sample_count} sample pair(s); missing FASTQ files were found."
        )
        result.suggestions.append("Check FASTQ file names or adjust Read1/Read2 suffix settings.")
    elif result.extra_fastq_files:
        result.status = "warning"
        result.messages.append(
            f"All {result.matched_pairs} sample pair(s) matched, but extra FASTQ files were found."
        )
        result.suggestions.append("Extra FASTQ files will not be used unless they match metadata SampleID values.")
    else:
        result.status = "passed"
        result.messages.append(f"All {result.matched_pairs} sample pair(s) matched.")

    return result
