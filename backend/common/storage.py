"""
Provider-neutral file storage for raw dataset bytes (Phase I-1).

Raw uploaded data NEVER lives in PostgreSQL. It is written through this
abstraction so a future object-storage backend can be swapped in without any
change to domain code (services only ever see ``get_file_store()`` +
``FileStore``).

Storage keys are generated server-side from record ids + a content checksum.
User-supplied filenames are metadata only and are never used as a path fragment.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO, Protocol

from django.conf import settings


class FileStore(Protocol):
    def save(self, key: str, fileobj: BinaryIO, *, content_type: str = "") -> str: ...
    def open(self, ref: str) -> BinaryIO: ...
    def exists(self, ref: str) -> bool: ...
    def delete(self, ref: str) -> None: ...
    def size(self, ref: str) -> int: ...


_SAFE_SEGMENT_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.="
)


def _validate_key(key: str) -> str:
    """
    Keys are produced by ``build_dataset_key`` — server-side, from uuids + a hex
    checksum. This is a defence-in-depth check that the key is a plain relative
    path of safe segments (no ``..``, no absolute path, no traversal), so even a
    bug upstream cannot escape the storage root.
    """
    if not key or key != key.strip("/"):
        raise ValueError("invalid storage key")
    parts = key.split("/")
    for part in parts:
        if part in ("", ".", "..") or any(ch not in _SAFE_SEGMENT_CHARS for ch in part):
            raise ValueError(f"invalid storage key segment: {part!r}")
    return key


class LocalFileStore:
    """Filesystem-backed FileStore rooted at ``DATA_STORAGE_ROOT``."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _abs(self, key: str) -> Path:
        _validate_key(key)
        candidate = (self.root / key).resolve()
        # candidate must be strictly inside root
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("resolved path escapes storage root")
        return candidate

    def save(self, key: str, fileobj: BinaryIO, *, content_type: str = "") -> str:
        path = self._abs(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fileobj.seek(0)
        except (OSError, AttributeError):
            pass
        with open(path, "wb") as out:
            shutil.copyfileobj(fileobj, out, length=1024 * 1024)
        return key

    def open(self, ref: str) -> BinaryIO:
        return open(self._abs(ref), "rb")

    def exists(self, ref: str) -> bool:
        try:
            return self._abs(ref).is_file()
        except ValueError:
            return False

    def delete(self, ref: str) -> None:
        try:
            self._abs(ref).unlink(missing_ok=True)
        except ValueError:
            pass

    def size(self, ref: str) -> int:
        return self._abs(ref).stat().st_size


def build_dataset_key(project_id, dataset_id, checksum: str, ext: str) -> str:
    """Deterministic, server-generated storage key. No user input."""
    ext = "".join(ch for ch in ext.lower() if ch.isalnum()) or "bin"
    return (
        f"projects/{project_id}/datasets/{dataset_id}/{checksum}/data.{ext}"
    )


def get_file_store() -> FileStore:
    return LocalFileStore(settings.DATA_STORAGE_ROOT)


def local_path(ref: str) -> str:
    """
    Absolute filesystem path for a stored object — ONLY valid for the local
    backend. Used by the DuckDB execution boundary (a subprocess that lives
    outside Django) to materialise a dataset into an in-memory table. The path
    is derived from a confined FileStore key, never from user input.
    """
    store = get_file_store()
    if not isinstance(store, LocalFileStore):  # pragma: no cover - future backends
        raise RuntimeError("local_path is only available for LocalFileStore")
    return str(store._abs(ref))
