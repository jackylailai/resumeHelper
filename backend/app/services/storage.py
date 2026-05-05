from __future__ import annotations

import hashlib
from pathlib import Path

from backend.app.config import get_settings


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_path(storage_dir: Path, name: str) -> Path:
    # Reject any path traversal attempt
    resolved = (storage_dir / name).resolve()
    if not resolved.is_relative_to(storage_dir.resolve()):
        raise ValueError(f"Unsafe storage path: {name!r}")
    return resolved


def save(data: bytes, fhash: str, ext: str) -> str:
    """Persist file bytes; return path relative to STORAGE_DIR."""
    storage_dir = get_settings().storage_dir
    filename = f"{fhash}.{ext.lstrip('.')}"
    dest = _safe_path(storage_dir, filename)
    if not dest.exists():
        dest.write_bytes(data)
    return filename


def read(relative_path: str) -> bytes:
    storage_dir = get_settings().storage_dir
    path = _safe_path(storage_dir, relative_path)
    return path.read_bytes()
