"""Shared helpers for OTU and ASV workflows."""

from __future__ import annotations

import os
import re
import shutil
from typing import Any, Dict, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.yaml")
DEFAULT_VSEARCH_WINDOWS_PATH = os.path.join(
    PROJECT_ROOT, "bin", "windows", "vsearch.exe"
)
DEFAULT_USEARCH_WINDOWS_PATH = os.path.join(
    PROJECT_ROOT, "bin", "windows", "usearch.exe"
)
DEFAULT_VSEARCH_POSIX_PATH = os.path.join(PROJECT_ROOT, "bin", "vsearch")
DEFAULT_USEARCH_POSIX_PATH = os.path.join(PROJECT_ROOT, "bin", "usearch")

try:
    import yaml
    from yaml import YAMLError
except ModuleNotFoundError:
    yaml = None
    YAMLError = ValueError


def parse_simple_yaml_defaults(config_text: str) -> Dict[str, Any]:
    """Parse the limited config structure used by this project."""

    section: Optional[str] = None
    parsed: Dict[str, Dict[str, str]] = {}

    for raw_line in config_text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        if not raw_line.startswith((" ", "\t")) and line.endswith(":"):
            section = line[:-1].strip()
            parsed.setdefault(section, {})
            continue

        if section is None:
            continue

        stripped = line.strip()
        if ":" not in stripped:
            continue

        key, value = stripped.split(":", 1)
        parsed[section][key.strip()] = value.strip()

    return parsed


def load_config_data(resolved_config_path: str) -> Dict[str, Any]:
    """Load configuration data from YAML."""

    with open(resolved_config_path, "r", encoding="utf-8") as handle:
        config_text = handle.read()

    if yaml is not None:
        try:
            return yaml.safe_load(config_text) or {}
        except YAMLError as exc:
            raise ValueError(
                f"Failed to parse YAML config: {resolved_config_path}"
            ) from exc

    return parse_simple_yaml_defaults(config_text)


def resolve_executable(
    executable_name: str,
    configured_path: Optional[str] = None,
    windows_default_path: Optional[str] = None,
    label: Optional[str] = None,
) -> str:
    """Resolve a usable executable path."""

    resolved_label = label or executable_name
    candidates = []

    if configured_path:
        candidates.append(os.path.abspath(configured_path))

    path_hit = shutil.which(executable_name)
    if path_hit:
        candidates.append(path_hit)

    if os.name == "nt" and windows_default_path:
        candidates.append(windows_default_path)
    elif os.name != "nt":
        normalized_name = executable_name.lower()
        if normalized_name == "usearch":
            candidates.append(DEFAULT_USEARCH_POSIX_PATH)
            candidates.append(os.path.join(PROJECT_ROOT, "bin", "linux", "usearch"))
        elif normalized_name == "vsearch":
            candidates.append(DEFAULT_VSEARCH_POSIX_PATH)
            candidates.append(os.path.join(PROJECT_ROOT, "bin", "linux", "vsearch"))

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate

    if configured_path:
        raise FileNotFoundError(
            f"{resolved_label} executable not found: {os.path.abspath(configured_path)}"
        )

    raise FileNotFoundError(
        f"Unable to locate {resolved_label}. Install it on PATH or provide an explicit executable path."
    )


def ensure_input_file(path: str, label: str) -> str:
    """Validate and resolve an input file path."""

    if not path:
        raise ValueError(f"{label} is required.")

    resolved_path = os.path.abspath(path)
    if not os.path.isfile(resolved_path):
        raise FileNotFoundError(f"{label} not found: {resolved_path}")

    return resolved_path


def ensure_input_fasta(input_fasta: str) -> str:
    """Validate and resolve an input FASTA path."""

    return ensure_input_file(input_fasta, "input_fasta")


def validate_threads(threads: int) -> int:
    """Validate a positive thread count."""

    try:
        parsed_threads = int(threads)
    except (TypeError, ValueError) as exc:
        raise ValueError("threads must be an integer greater than 0.") from exc

    if parsed_threads < 1:
        raise ValueError("threads must be an integer greater than 0.")

    return parsed_threads


def validate_positive_int(name: str, value: Any, minimum: int = 1) -> int:
    """Validate a positive integer parameter."""

    try:
        parsed_value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer greater than or equal to {minimum}.") from exc

    if parsed_value < minimum:
        raise ValueError(f"{name} must be an integer greater than or equal to {minimum}.")

    return parsed_value


def parse_abundance(header: str) -> int:
    """Parse an abundance value from a FASTA header."""

    match = re.search(r";size=(\d+)", header)
    if match:
        return int(match.group(1))
    return 1


def filter_fasta_by_minsize(
    input_fasta: str,
    output_fasta: str,
    minsize: int,
) -> Dict[str, int]:
    """Filter FASTA records by abundance encoded as ;size=<int> in the header."""

    kept_records = 0
    skipped_records = 0
    total_records = 0
    header: Optional[str] = None
    sequence_lines: list[str] = []

    with open(input_fasta, "r", encoding="utf-8") as source, open(
        output_fasta, "w", encoding="ascii", newline="\n"
    ) as destination:
        for raw_line in source:
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith(">"):
                if header is not None:
                    abundance = parse_abundance(header)
                    total_records += 1
                    if abundance >= minsize:
                        destination.write(f">{header}\n")
                        for seq_line in sequence_lines:
                            destination.write(f"{seq_line}\n")
                        kept_records += 1
                    else:
                        skipped_records += 1

                header = line[1:]
                sequence_lines = []
            else:
                sequence_lines.append(line)

        if header is not None:
            abundance = parse_abundance(header)
            total_records += 1
            if abundance >= minsize:
                destination.write(f">{header}\n")
                for seq_line in sequence_lines:
                    destination.write(f"{seq_line}\n")
                kept_records += 1
            else:
                skipped_records += 1

    return {
        "total_records": total_records,
        "kept_records": kept_records,
        "skipped_records": skipped_records,
    }


def relabel_fasta(input_fasta: str, output_fasta: str, prefix: str) -> int:
    """Relabel FASTA headers sequentially while preserving sequences."""

    written_records = 0
    header: Optional[str] = None
    sequence_lines: list[str] = []

    with open(input_fasta, "r", encoding="utf-8") as source, open(
        output_fasta, "w", encoding="ascii", newline="\n"
    ) as destination:
        for raw_line in source:
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith(">"):
                if header is not None:
                    written_records += 1
                    destination.write(f">{prefix}{written_records}\n")
                    for seq_line in sequence_lines:
                        destination.write(f"{seq_line}\n")

                header = line[1:]
                sequence_lines = []
            else:
                sequence_lines.append(line)

        if header is not None:
            written_records += 1
            destination.write(f">{prefix}{written_records}\n")
            for seq_line in sequence_lines:
                destination.write(f"{seq_line}\n")

    return written_records


def replace_header_text(
    input_fasta: str,
    output_fasta: str,
    source_text: str,
    target_text: str,
) -> int:
    """Replace text in FASTA headers only."""

    written_records = 0

    with open(input_fasta, "r", encoding="utf-8") as source, open(
        output_fasta, "w", encoding="ascii", newline="\n"
    ) as destination:
        for raw_line in source:
            if raw_line.startswith(">"):
                written_records += 1
                destination.write(
                    raw_line.replace(source_text, target_text, 1).rstrip("\r\n") + "\n"
                )
            else:
                destination.write(raw_line.rstrip("\r\n") + "\n")

    return written_records


def normalize_text_file_line_endings(
    path: str,
    line_ending: str = "\n",
) -> None:
    """Rewrite a text file with normalized line endings."""

    with open(path, "r", encoding="utf-8", newline=None) as source:
        content = source.read()

    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if line_ending != "\n":
        normalized = normalized.replace("\n", line_ending)

    with open(path, "w", encoding="utf-8", newline="") as destination:
        destination.write(normalized)


def reorder_fasta_by_template(
    input_fasta: str,
    template_fasta: str,
    output_fasta: str,
) -> Dict[str, int]:
    """Reorder FASTA records to follow the header order in a template FASTA."""

    template_bytes = b""
    with open(template_fasta, "rb") as template_binary:
        template_bytes = template_binary.read()
    line_ending = "\r\n" if b"\r\n" in template_bytes else "\n"

    template_headers: list[str] = []
    with open(template_fasta, "r", encoding="utf-8") as template_handle:
        for raw_line in template_handle:
            if raw_line.startswith(">"):
                template_headers.append(raw_line.strip()[1:])

    records: Dict[str, list[str]] = {}
    original_order: list[str] = []
    current_header: Optional[str] = None
    current_sequence: list[str] = []

    with open(input_fasta, "r", encoding="utf-8") as source:
        for raw_line in source:
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith(">"):
                if current_header is not None:
                    records[current_header] = list(current_sequence)
                    original_order.append(current_header)
                current_header = line[1:]
                current_sequence = []
            else:
                current_sequence.append(line)

        if current_header is not None:
            records[current_header] = list(current_sequence)
            original_order.append(current_header)

    written = 0
    used_headers: set[str] = set()

    with open(output_fasta, "w", encoding="ascii", newline="") as destination:
        for header in template_headers:
            if header in records:
                destination.write(f">{header}{line_ending}")
                for seq_line in records[header]:
                    destination.write(f"{seq_line}{line_ending}")
                used_headers.add(header)
                written += 1

        for header in original_order:
            if header not in used_headers:
                destination.write(f">{header}{line_ending}")
                for seq_line in records[header]:
                    destination.write(f"{seq_line}{line_ending}")
                written += 1

    return {
        "template_headers": len(template_headers),
        "input_records": len(records),
        "written_records": written,
        "matched_headers": len(used_headers),
    }
