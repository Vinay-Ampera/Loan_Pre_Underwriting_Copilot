"""Where uploaded files live. One small interface so a later object store or a Docker volume can
replace the local disk without touching the routes (Stage 10, item 14).

A file is addressed by the `key` that `put` returns (for the local store that is the path, which
is what `documents.file_path` and the pipeline's `DocumentRef.path` already hold). Files are
written under generated names, never under an uploaded name. Nothing here is public: files are
served only by authenticated routes.

Next to each file the desk keeps a small "read result" (what the one early read found: type,
fields, quality flags; never the raw text). It is a separate object so a file and what was read
from it are deleted together.
"""

import os
import uuid
from pathlib import Path
from typing import Protocol
from uuid import UUID

from app.intake.readcache import READ_SUFFIX


class FileStore(Protocol):
    def put(self, case_id: UUID, data: bytes, ext: str) -> str: ...
    def read(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def case_bytes(self, case_id: UUID) -> int: ...
    def put_read_result(self, key: str, blob: bytes) -> None: ...
    def get_read_result(self, key: str) -> bytes | None: ...


class LocalFileStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _folder(self, case_id: UUID) -> Path:
        return self.root / str(case_id)

    def put(self, case_id: UUID, data: bytes, ext: str) -> str:
        folder = self._folder(case_id)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{uuid.uuid4().hex}{ext}"
        path.write_bytes(data)
        return str(path)

    def read(self, key: str) -> bytes:
        return Path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return Path(key).is_file()

    def delete(self, key: str) -> None:
        Path(key).unlink(missing_ok=True)
        Path(key + READ_SUFFIX).unlink(missing_ok=True)

    def case_bytes(self, case_id: UUID) -> int:
        folder = self._folder(case_id)
        if not folder.exists():
            return 0
        return sum(os.path.getsize(p) for p in folder.glob("*") if not p.name.endswith(READ_SUFFIX))

    def put_read_result(self, key: str, blob: bytes) -> None:
        Path(key + READ_SUFFIX).write_bytes(blob)

    def get_read_result(self, key: str) -> bytes | None:
        p = Path(key + READ_SUFFIX)
        return p.read_bytes() if p.is_file() else None
