"""Taxonomic annotation workflow based on VSEARCH sintax."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Sequence

from src.utils.command_runner import run_command

from .database_registry import (
    BUILTIN_DATABASES,
    canonicalize_database_identifier,
    resolve_database_record,
)
from .workflow_common import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_VSEARCH_WINDOWS_PATH,
    ensure_input_fasta,
    load_config_data,
    normalize_text_file_line_endings,
    resolve_executable,
    validate_positive_int,
    validate_threads,
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATABASE_DIRECTORY = os.path.join(PROJECT_ROOT, "databas")
DATABASE_FILE_MAP = {
    name: os.path.basename(str(record["sequence_path"]))
    for name, record in BUILTIN_DATABASES.items()
}
DATABASE_ALIASES = {}
for _database_name, _database_record in BUILTIN_DATABASES.items():
    DATABASE_ALIASES[_database_name] = _database_name
    for _database_alias in _database_record.get("aliases", []):
        DATABASE_ALIASES[str(_database_alias).strip().lower()] = _database_name
FALLBACK_VSEARCH_SINTAX_DEFAULTS = {
    "database": "rdp_16s_v18",
    "sintax_cutoff": 0.1,
}


def _coerce_database(value: Any) -> str:
    if value is None:
        raise ValueError("database must be a registered database name or FASTA path.")

    database = str(value).strip()
    if not database:
        raise ValueError("database must be a registered database name or FASTA path.")
    return canonicalize_database_identifier(database)


def _resolve_sintax_cutoff(
    sintax_cutoff: Optional[float],
    config_path: Optional[str],
) -> float:
    if sintax_cutoff is None:
        resolved_cutoff = load_vsearch_sintax_defaults(config_path)["sintax_cutoff"]
    else:
        try:
            resolved_cutoff = float(sintax_cutoff)
        except (TypeError, ValueError) as exc:
            raise ValueError("sintax_cutoff must be a number between 0 and 1.") from exc

    if not 0 <= resolved_cutoff <= 1:
        raise ValueError("sintax_cutoff must be a number between 0 and 1.")

    return resolved_cutoff


def _resolve_optional_threads(threads: Optional[int]) -> Optional[int]:
    if threads is None:
        return None
    return validate_threads(threads)


def _resolve_wordlength(wordlength: Optional[int]) -> Optional[int]:
    if wordlength is None:
        return None

    resolved_wordlength = validate_positive_int("wordlength", wordlength, minimum=3)
    if resolved_wordlength > 15:
        raise ValueError("wordlength must be an integer between 3 and 15.")

    return resolved_wordlength


def _resolve_strand(strand: Optional[str]) -> Optional[str]:
    if strand is None:
        return None

    normalized = str(strand).strip().lower()
    if normalized not in {"plus", "both"}:
        raise ValueError("strand must be either 'plus' or 'both'.")

    return normalized


def _resolve_dbmask(dbmask: Optional[str]) -> Optional[str]:
    if dbmask is None:
        return None

    normalized = str(dbmask).strip().lower()
    if normalized not in {"none", "dust", "soft"}:
        raise ValueError("dbmask must be one of: none, dust, soft.")

    return normalized


def _resolve_randseed(randseed: Optional[int]) -> Optional[int]:
    if randseed is None:
        return None
    return validate_positive_int("randseed", randseed, minimum=1)


def _build_sintax_command(
    vsearch_executable: str,
    input_fasta: str,
    database_path: str,
    sintax_cutoff: float,
    output_path: str,
    threads: Optional[int] = None,
    wordlength: Optional[int] = None,
    strand: Optional[str] = None,
    dbmask: Optional[str] = None,
    randseed: Optional[int] = None,
    sintax_random: bool = False,
) -> Sequence[str]:
    command: list[str] = [
        vsearch_executable,
        "--sintax",
        input_fasta,
        "--db",
        database_path,
        "--sintax_cutoff",
        f"{sintax_cutoff:.4f}",
        "--tabbedout",
        output_path,
    ]

    if threads is not None:
        command.extend(["--threads", str(threads)])
    if wordlength is not None:
        command.extend(["--wordlength", str(wordlength)])
    if strand is not None:
        command.extend(["--strand", strand])
    if dbmask is not None:
        command.extend(["--dbmask", dbmask])
    if randseed is not None:
        command.extend(["--randseed", str(randseed)])
    if sintax_random:
        command.append("--sintax_random")

    return command


def load_vsearch_sintax_defaults(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load default VSEARCH sintax settings from config.yaml."""

    resolved_config_path = os.path.abspath(config_path or DEFAULT_CONFIG_PATH)
    default_config_path = os.path.abspath(DEFAULT_CONFIG_PATH)

    if not os.path.exists(resolved_config_path):
        if resolved_config_path == default_config_path:
            return dict(FALLBACK_VSEARCH_SINTAX_DEFAULTS)
        raise FileNotFoundError(f"Config file not found: {resolved_config_path}")

    config_data = load_config_data(resolved_config_path)
    defaults = config_data.get("vsearch_sintax_defaults", {})

    raw_database = defaults.get(
        "database",
        defaults.get("reference_db", FALLBACK_VSEARCH_SINTAX_DEFAULTS["database"]),
    )
    raw_sintax_cutoff = defaults.get(
        "sintax_cutoff", FALLBACK_VSEARCH_SINTAX_DEFAULTS["sintax_cutoff"]
    )

    try:
        sintax_cutoff = float(raw_sintax_cutoff)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Invalid config value for vsearch_sintax_defaults.sintax_cutoff."
        ) from exc

    if not 0 <= sintax_cutoff <= 1:
        raise ValueError("vsearch_sintax_defaults.sintax_cutoff must be between 0 and 1.")

    return {
        "database": _coerce_database(raw_database),
        "sintax_cutoff": sintax_cutoff,
    }


def resolve_vsearch_executable(vsearch_path: Optional[str] = None) -> str:
    """Resolve a usable VSEARCH executable path."""

    return resolve_executable(
        executable_name="vsearch",
        configured_path=vsearch_path,
        windows_default_path=DEFAULT_VSEARCH_WINDOWS_PATH,
        label="VSEARCH",
    )


def resolve_sintax_database_path(
    database: Optional[str] = None,
    config_path: Optional[str] = None,
) -> tuple[str, str]:
    """Resolve the selected database name, alias, or FASTA path."""

    if database is None:
        database_name = load_vsearch_sintax_defaults(config_path)["database"]
    else:
        database_name = _coerce_database(database)

    try:
        database_record = resolve_database_record(
            database_name,
            require_exists=True,
            include_hash=False,
        )
    except KeyError as exc:
        raise ValueError(str(exc)) from exc

    return str(database_record["name"]), str(database_record["path"])


def run_vsearch_sintax(
    input_fasta: str,
    output_dir: str,
    threads: Optional[int] = None,
    database: Optional[str] = None,
    sintax_cutoff: Optional[float] = None,
    wordlength: Optional[int] = None,
    strand: Optional[str] = None,
    dbmask: Optional[str] = None,
    randseed: Optional[int] = None,
    sintax_random: bool = False,
    config_path: Optional[str] = None,
    vsearch_path: Optional[str] = None,
    output_annotation_path: Optional[str] = None,
    command_timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Run taxonomic annotation with VSEARCH sintax."""

    resolved_input_fasta = ensure_input_fasta(input_fasta)
    resolved_output_dir = os.path.abspath(output_dir)
    os.makedirs(resolved_output_dir, exist_ok=True)

    resolved_threads = _resolve_optional_threads(threads)
    resolved_database, resolved_database_path = resolve_sintax_database_path(
        database=database,
        config_path=config_path,
    )
    resolved_sintax_cutoff = _resolve_sintax_cutoff(sintax_cutoff, config_path)
    resolved_wordlength = _resolve_wordlength(wordlength)
    resolved_strand = _resolve_strand(strand)
    resolved_dbmask = _resolve_dbmask(dbmask)
    resolved_randseed = _resolve_randseed(randseed)
    resolved_vsearch = resolve_vsearch_executable(vsearch_path)

    default_output_filename = (
        f"{os.path.splitext(os.path.basename(resolved_input_fasta))[0]}.sintax"
    )
    default_output_path = os.path.join(resolved_output_dir, default_output_filename)
    final_output_path = os.path.abspath(output_annotation_path or default_output_path)
    parent_dir = os.path.dirname(final_output_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    print("[VSEARCH SINTAX] Starting taxonomic annotation workflow.")
    print(f"[VSEARCH SINTAX] Input FASTA: {resolved_input_fasta}")
    print(f"[VSEARCH SINTAX] Output table: {final_output_path}")
    print(f"[VSEARCH SINTAX] Database preset: {resolved_database}")
    print(f"[VSEARCH SINTAX] Database FASTA: {resolved_database_path}")
    print(f"[VSEARCH SINTAX] SINTAX cutoff: {resolved_sintax_cutoff}")
    print(
        "[VSEARCH SINTAX] Threads: "
        f"{resolved_threads if resolved_threads is not None else 'vsearch default'}"
    )
    if resolved_wordlength is not None:
        print(f"[VSEARCH SINTAX] Wordlength: {resolved_wordlength}")
    if resolved_strand is not None:
        print(f"[VSEARCH SINTAX] Strand: {resolved_strand}")
    if resolved_dbmask is not None:
        print(f"[VSEARCH SINTAX] Database mask: {resolved_dbmask}")
    if resolved_randseed is not None:
        print(f"[VSEARCH SINTAX] Random seed: {resolved_randseed}")
    print(f"[VSEARCH SINTAX] SINTAX random mode: {sintax_random}")
    print(f"[VSEARCH SINTAX] VSEARCH executable: {resolved_vsearch}")

    run_command(
        _build_sintax_command(
            vsearch_executable=resolved_vsearch,
            input_fasta=resolved_input_fasta,
            database_path=resolved_database_path,
            sintax_cutoff=resolved_sintax_cutoff,
            output_path=final_output_path,
            threads=resolved_threads,
            wordlength=resolved_wordlength,
            strand=resolved_strand,
            dbmask=resolved_dbmask,
            randseed=resolved_randseed,
            sintax_random=sintax_random,
        ),
        timeout=command_timeout,
    )
    normalize_text_file_line_endings(final_output_path, line_ending="\n")

    print("[VSEARCH SINTAX] Workflow finished successfully.")

    return {
        "database": resolved_database,
        "database_path": resolved_database_path,
        "sintax_cutoff": resolved_sintax_cutoff,
        "threads": resolved_threads,
        "command_timeout": command_timeout,
        "wordlength": resolved_wordlength,
        "strand": resolved_strand,
        "dbmask": resolved_dbmask,
        "randseed": resolved_randseed,
        "sintax_random": sintax_random,
        "vsearch": resolved_vsearch,
        "input_fasta": resolved_input_fasta,
        "sintax_table": final_output_path,
    }
