"""Files on local disk under STORAGE_DIR. Keys look like "meetings/7/audio.wav"."""

import asyncio
import shutil
from pathlib import Path
from typing import BinaryIO

from starlette.datastructures import UploadFile  # FastAPI's UploadFile subclasses this

_CHUNK_BYTES = 1024 * 1024


class UploadTooLargeError(Exception):
    pass


def meeting_key(meeting_id: int, name: str) -> str:
    return f"meetings/{meeting_id}/{name}"


def _copy_limited(source: BinaryIO, destination: Path, max_bytes: int) -> int:
    written = 0
    try:
        with destination.open("wb") as out:
            while chunk := source.read(_CHUNK_BYTES):
                written += len(chunk)
                if written > max_bytes:
                    raise UploadTooLargeError
                out.write(chunk)
    except UploadTooLargeError:
        destination.unlink(missing_ok=True)
        raise
    return written


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def path(self, key: str) -> Path:
        """Absolute path for a key, creating its folder. Keys may not leave the root."""
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError(f"storage key escapes the storage folder: {key!r}")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    async def save_upload(self, key: str, upload: UploadFile, *, max_bytes: int) -> int:
        """Copy an upload to disk in 1 MiB chunks; over max_bytes, delete it and raise."""
        return await asyncio.to_thread(_copy_limited, upload.file, self.path(key), max_bytes)

    def delete_prefix(self, prefix: str) -> None:
        target = self.path(prefix)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
