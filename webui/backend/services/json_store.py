"""Small JSON persistence helpers for local Web UI state."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
from typing import Any


def read_json(path: Path, default: Any) -> Any:
    """Read JSON from path, returning default when missing."""

    if not path.exists():
        return default
    last_error: Exception | None = None
    for _ in range(10):
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (PermissionError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.03)
    if last_error is not None:
        raise last_error
    return default


def write_json(path: Path, payload: Any) -> None:
    """Atomically write JSON payload to path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
        suffix=".tmp",
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    last_error: PermissionError | None = None
    for _ in range(20):
        try:
            temp_path.replace(path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05)
    if last_error is not None:
        raise last_error
