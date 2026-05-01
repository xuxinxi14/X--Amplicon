"""Database registry helpers for reference FASTA management."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from typing import Any, Mapping

import yaml

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_DATABASE_REGISTRY_PATH = os.path.join(PROJECT_ROOT, "databases.yaml")
EXAMPLE_DATABASE_REGISTRY_PATH = os.path.join(PROJECT_ROOT, "databases.example.yaml")
DEFAULT_HASH_CHUNK_SIZE = 1024 * 1024
DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
FASTA_EXTENSIONS = {
    ".fa",
    ".fasta",
    ".fna",
    ".ffn",
    ".fas",
    ".fa.gz",
    ".fasta.gz",
    ".fna.gz",
}

BUILTIN_DATABASES: dict[str, dict[str, Any]] = {
    "rdp_16s_v18": {
        "version": "v18",
        "taxonomy_format": "sintax",
        "type": "taxonomy_annotation",
        "roles": ["taxonomy_annotation", "chimera_reference"],
        "sequence_path": os.path.join("database", "rdp_16s_v18.fa"),
        "aliases": [
            "rdp",
            "rdp_16s_v18.fa",
            os.path.join("databas", "rdp_16s_v18.fa"),
        ],
    },
    "silva_16s_v123": {
        "version": "v123",
        "taxonomy_format": "sintax",
        "type": "taxonomy_annotation",
        "roles": ["taxonomy_annotation"],
        "sequence_path": os.path.join("database", "silva_16s_v123.fa"),
        "aliases": [
            "silva",
            "silva_16s_v123.fa",
            os.path.join("databas", "silva_16s_v123.fa"),
        ],
    },
}


def _compact_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in record.items() if value not in (None, [], {})}


def _resolve_registry_path(registry_path: str | None = None) -> str:
    return os.path.abspath(registry_path or DEFAULT_DATABASE_REGISTRY_PATH)


def _normalize_identifier(value: str) -> str:
    return str(value).strip().lower().replace("\\", "/")


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _read_registry_file(registry_path: str) -> dict[str, Any]:
    if not os.path.exists(registry_path):
        return {}
    with open(registry_path, "r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Database registry must contain a YAML mapping: {registry_path}")
    return loaded


def _write_registry_file(registry_path: str, payload: Mapping[str, Any]) -> None:
    parent_dir = os.path.dirname(os.path.abspath(registry_path))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    with open(registry_path, "w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(
            dict(payload),
            handle,
            allow_unicode=True,
            sort_keys=False,
        )


def _iter_registry_entries(payload: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    raw_databases = payload.get("databases", {})
    entries: list[tuple[str, Mapping[str, Any]]] = []
    if isinstance(raw_databases, Mapping):
        for name, record in raw_databases.items():
            if isinstance(record, Mapping):
                entries.append((str(name), record))
        return entries

    if isinstance(raw_databases, list):
        for record in raw_databases:
            if not isinstance(record, Mapping):
                continue
            name = record.get("name")
            if name:
                entries.append((str(name), record))
        return entries

    raise ValueError("Database registry field 'databases' must be a mapping or a list.")


def _resolve_sequence_path(sequence_path: str, base_dir: str) -> str:
    text = str(sequence_path).strip()
    if os.path.isabs(text):
        return os.path.abspath(text)
    return os.path.abspath(os.path.join(base_dir, text))


def _portable_path(path: str, base_dir: str) -> str:
    resolved_path = os.path.abspath(path)
    resolved_base = os.path.abspath(base_dir)
    try:
        relative = os.path.relpath(resolved_path, resolved_base)
    except ValueError:
        return resolved_path
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        return resolved_path
    return relative.replace("\\", "/")


def _get_expected_hash(record: Mapping[str, Any]) -> str | None:
    for key in ("sha256", "hash", "checksum"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def _normalize_database_record(
    name: str,
    raw_record: Mapping[str, Any],
    *,
    base_dir: str,
    source: str,
    registry_path: str | None = None,
) -> dict[str, Any]:
    clean_name = str(raw_record.get("name", name)).strip()
    if not clean_name:
        raise ValueError("Database name cannot be empty.")

    sequence_path = (
        raw_record.get("sequence_path")
        or raw_record.get("path")
        or raw_record.get("fasta")
        or raw_record.get("file")
    )
    if not sequence_path:
        raise ValueError(f"Database '{clean_name}' is missing sequence_path.")

    database_type = raw_record.get("type", raw_record.get("database_type"))
    record = {
        "name": clean_name,
        "version": raw_record.get("version"),
        "taxonomy_format": raw_record.get("taxonomy_format"),
        "type": database_type,
        "roles": _as_list(raw_record.get("roles")),
        "sequence_path": str(sequence_path),
        "path": _resolve_sequence_path(str(sequence_path), base_dir),
        "expected_sha256": _get_expected_hash(raw_record),
        "aliases": _as_list(raw_record.get("aliases")),
        "source": source,
        "registry_path": None if registry_path is None else os.path.abspath(registry_path),
        "description": raw_record.get("description"),
        "url": raw_record.get("url"),
        "citation": raw_record.get("citation"),
    }
    return _compact_record(record)


def _file_sha256(path: str, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _attach_file_metadata(record: Mapping[str, Any], *, include_hash: bool) -> dict[str, Any]:
    enriched = dict(record)
    path = os.path.abspath(str(enriched["path"]))
    enriched["path"] = path
    enriched["exists"] = os.path.exists(path)
    if not enriched["exists"]:
        return enriched

    enriched["is_file"] = os.path.isfile(path)
    enriched["is_dir"] = os.path.isdir(path)
    try:
        stat = os.stat(path)
    except OSError as exc:
        enriched["error"] = str(exc)
        return enriched

    enriched["size_bytes"] = int(stat.st_size)
    enriched["modified_at"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
    if include_hash and os.path.isfile(path):
        try:
            enriched["sha256"] = _file_sha256(path)
        except OSError as exc:
            enriched["sha256_error"] = str(exc)

    expected_sha256 = enriched.get("expected_sha256")
    observed_sha256 = enriched.get("sha256")
    if isinstance(expected_sha256, str) and isinstance(observed_sha256, str):
        enriched["hash_matches"] = expected_sha256.lower() == observed_sha256.lower()
    return enriched


def _is_probable_path(value: str) -> bool:
    text = str(value).strip()
    if not text:
        return False
    if os.path.isabs(text) or "/" in text or "\\" in text:
        return True
    lowered = text.lower()
    return any(lowered.endswith(extension) for extension in FASTA_EXTENSIONS)


def _direct_path_record(value: str, *, include_hash: bool) -> dict[str, Any]:
    path = os.path.abspath(str(value))
    stem = os.path.basename(path)
    for suffix in (".fa.gz", ".fasta.gz", ".fna.gz"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    else:
        stem = os.path.splitext(stem)[0]

    record = {
        "name": stem or os.path.basename(path),
        "version": None,
        "taxonomy_format": None,
        "type": "direct_path",
        "roles": [],
        "sequence_path": str(value),
        "path": path,
        "aliases": [],
        "source": "path",
    }
    return _attach_file_metadata(_compact_record(record), include_hash=include_hash)


def load_database_registry(
    registry_path: str | None = None,
    *,
    include_builtin: bool = True,
) -> dict[str, dict[str, Any]]:
    """Load database records from the registry and built-in compatibility entries."""

    resolved_registry_path = _resolve_registry_path(registry_path)
    records: dict[str, dict[str, Any]] = {}
    if include_builtin:
        for name, raw_record in BUILTIN_DATABASES.items():
            records[name] = _normalize_database_record(
                name,
                raw_record,
                base_dir=PROJECT_ROOT,
                source="builtin",
            )

    if os.path.exists(resolved_registry_path):
        payload = _read_registry_file(resolved_registry_path)
        registry_base_dir = os.path.dirname(resolved_registry_path)
        for name, raw_record in _iter_registry_entries(payload):
            normalized = _normalize_database_record(
                name,
                raw_record,
                base_dir=registry_base_dir,
                source="registry",
                registry_path=resolved_registry_path,
            )
            records[normalized["name"]] = normalized

    return records


def _build_lookup(records: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for name, record in records.items():
        lookup[_normalize_identifier(name)] = str(name)
        lookup[_normalize_identifier(str(record.get("name", name)))] = str(name)
        for alias in _as_list(record.get("aliases")):
            lookup[_normalize_identifier(alias)] = str(name)
    return lookup


def resolve_database_record(
    name_or_path: str,
    registry_path: str | None = None,
    *,
    include_builtin: bool = True,
    require_exists: bool = True,
    include_hash: bool = False,
) -> dict[str, Any]:
    """Resolve a registered database name, alias, or direct FASTA path."""

    if name_or_path is None or not str(name_or_path).strip():
        raise ValueError("Database name or path cannot be empty.")

    query = str(name_or_path).strip().strip("\"'`").strip()
    records = load_database_registry(registry_path, include_builtin=include_builtin)
    lookup = _build_lookup(records)
    normalized_query = _normalize_identifier(query)
    record_name = lookup.get(normalized_query)

    if record_name is None:
        candidate_path = os.path.abspath(query)
        for name, candidate in records.items():
            if os.path.abspath(str(candidate.get("path"))) == candidate_path:
                record_name = str(name)
                break

    if record_name is not None:
        record = _attach_file_metadata(records[record_name], include_hash=include_hash)
    elif _is_probable_path(query):
        record = _direct_path_record(query, include_hash=include_hash)
    else:
        known_names = ", ".join(sorted(records)) or "none"
        raise KeyError(
            "Database is not registered and does not look like a FASTA path: "
            f"{query}. Known databases: {known_names}. "
            "Use 'process.py register-database' to add it."
        )

    if require_exists and not record.get("exists"):
        raise FileNotFoundError(f"Database FASTA file not found: {record.get('path')}")
    return record


def canonicalize_database_identifier(
    name_or_path: str,
    registry_path: str | None = None,
    *,
    include_builtin: bool = True,
) -> str:
    """Return the canonical registered name when possible; otherwise return the input."""

    try:
        record = resolve_database_record(
            name_or_path,
            registry_path=registry_path,
            include_builtin=include_builtin,
            require_exists=False,
            include_hash=False,
        )
    except (FileNotFoundError, KeyError, ValueError):
        return str(name_or_path).strip()
    if record.get("source") == "path":
        return str(name_or_path).strip()
    return str(record.get("name") or name_or_path)


def list_databases(
    registry_path: str | None = None,
    *,
    include_builtin: bool = True,
    include_hash: bool = False,
) -> list[dict[str, Any]]:
    """List known database records with file metadata."""

    records = load_database_registry(registry_path, include_builtin=include_builtin)
    return [
        _attach_file_metadata(record, include_hash=include_hash)
        for _, record in sorted(records.items(), key=lambda item: item[0].lower())
    ]


def check_database(
    name_or_path: str,
    registry_path: str | None = None,
    *,
    include_builtin: bool = True,
    include_hash: bool = True,
) -> dict[str, Any]:
    """Check whether a database resolves to an existing FASTA and valid hash."""

    try:
        record = resolve_database_record(
            name_or_path,
            registry_path=registry_path,
            include_builtin=include_builtin,
            require_exists=False,
            include_hash=include_hash,
        )
    except (KeyError, ValueError) as exc:
        return {
            "status": "failed",
            "query": str(name_or_path),
            "message": str(exc),
        }

    if not record.get("exists"):
        return {
            **record,
            "status": "failed",
            "message": f"Database FASTA file not found: {record.get('path')}",
        }
    if record.get("hash_matches") is False:
        return {
            **record,
            "status": "failed",
            "message": "Database SHA-256 does not match the registry value.",
        }

    return {
        **record,
        "status": "passed",
        "message": "Database is available.",
    }


def register_database(
    name: str,
    sequence_path: str,
    *,
    version: str | None = None,
    taxonomy_format: str = "sintax",
    database_type: str = "taxonomy_annotation",
    registry_path: str | None = None,
    aliases: list[str] | tuple[str, ...] | None = None,
    roles: list[str] | tuple[str, ...] | None = None,
    sha256: str | None = None,
    compute_hash: bool = True,
    require_exists: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Register or update a database record in a YAML registry."""

    clean_name = str(name).strip()
    if not clean_name:
        raise ValueError("Database name cannot be empty.")
    if not DATABASE_NAME_PATTERN.match(clean_name):
        raise ValueError(
            "Database name can contain only letters, numbers, underscores, hyphens, and dots."
        )

    resolved_registry_path = _resolve_registry_path(registry_path)
    registry_dir = os.path.dirname(resolved_registry_path)
    resolved_sequence_path = os.path.abspath(sequence_path)
    if require_exists and not os.path.isfile(resolved_sequence_path):
        raise FileNotFoundError(f"Database FASTA file not found: {resolved_sequence_path}")

    observed_sha256: str | None = None
    if compute_hash and os.path.isfile(resolved_sequence_path):
        observed_sha256 = _file_sha256(resolved_sequence_path)
    expected_sha256 = sha256.strip().lower() if isinstance(sha256, str) and sha256.strip() else observed_sha256
    if sha256 and observed_sha256 and expected_sha256 != observed_sha256:
        raise ValueError("Provided SHA-256 does not match the database file.")

    payload = _read_registry_file(resolved_registry_path)
    raw_databases = payload.get("databases", {})
    if raw_databases in ({}, None):
        raw_databases = {}
    if not isinstance(raw_databases, dict):
        raise ValueError("Cannot update registry because 'databases' is not a mapping.")
    if clean_name in raw_databases and not overwrite:
        raise ValueError(
            f"Database '{clean_name}' already exists. Use overwrite=True to replace it."
        )

    entry = _compact_record(
        {
            "version": version,
            "taxonomy_format": taxonomy_format,
            "type": database_type,
            "roles": list(roles or ["taxonomy_annotation"]),
            "sequence_path": _portable_path(resolved_sequence_path, registry_dir),
            "sha256": expected_sha256,
            "aliases": list(aliases or []),
        }
    )
    raw_databases[clean_name] = entry
    payload["databases"] = raw_databases
    _write_registry_file(resolved_registry_path, payload)

    return check_database(
        clean_name,
        registry_path=resolved_registry_path,
        include_builtin=True,
        include_hash=compute_hash,
    )


def list_registered_databases(
    registry_path: str | None = None,
    include_builtin: bool = True,
    include_hash: bool = False,
) -> dict[str, Any]:
    """Agent tool wrapper for listing registered databases."""

    resolved_registry_path = _resolve_registry_path(registry_path)
    return {
        "status": "success",
        "registry_path": resolved_registry_path,
        "registry_exists": os.path.exists(resolved_registry_path),
        "databases": list_databases(
            registry_path=resolved_registry_path,
            include_builtin=include_builtin,
            include_hash=include_hash,
        ),
    }


def check_registered_database(
    database: str,
    registry_path: str | None = None,
    include_hash: bool = True,
) -> dict[str, Any]:
    """Agent tool wrapper for checking a registered database or FASTA path."""

    return check_database(database, registry_path=registry_path, include_hash=include_hash)


TOOL_DEFINITIONS = [
    {
        "name": "list_registered_databases",
        "description": (
            "List X-Amplicon reference databases from the optional databases.yaml "
            "registry plus built-in RDP/SILVA compatibility records."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "registry_path": {"type": "string"},
                "include_builtin": {"type": "boolean", "default": True},
                "include_hash": {"type": "boolean", "default": False},
            },
        },
        "fn": list_registered_databases,
    },
    {
        "name": "check_registered_database",
        "description": (
            "Check whether a database name, alias, or FASTA path resolves to an "
            "available file and optionally verify its SHA-256 hash."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "database": {"type": "string"},
                "registry_path": {"type": "string"},
                "include_hash": {"type": "boolean", "default": True},
            },
            "required": ["database"],
        },
        "fn": check_registered_database,
    },
    {
        "name": "register_database",
        "description": (
            "Register a reference FASTA in databases.yaml with name, version, "
            "taxonomy format, path, and SHA-256 metadata."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "sequence_path": {"type": "string"},
                "version": {"type": "string"},
                "taxonomy_format": {"type": "string", "default": "sintax"},
                "database_type": {"type": "string", "default": "taxonomy_annotation"},
                "registry_path": {"type": "string"},
                "aliases": {"type": "array", "items": {"type": "string"}},
                "roles": {"type": "array", "items": {"type": "string"}},
                "sha256": {"type": "string"},
                "compute_hash": {"type": "boolean", "default": True},
                "require_exists": {"type": "boolean", "default": True},
                "overwrite": {"type": "boolean", "default": False},
            },
            "required": ["name", "sequence_path"],
        },
        "fn": register_database,
    },
]
