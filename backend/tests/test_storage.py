import io

import pytest
from starlette.datastructures import UploadFile

from app.storage import LocalStorage, UploadTooLargeError, meeting_key


def test_meeting_key():
    assert meeting_key(7, "audio.wav") == "meetings/7/audio.wav"


def test_path_creates_parent_folders(tmp_path):
    path = LocalStorage(tmp_path).path("meetings/1/audio.wav")
    assert path.parent.is_dir() and path.is_absolute()


def test_keys_cannot_escape_the_storage_folder(tmp_path):
    with pytest.raises(ValueError):
        LocalStorage(tmp_path / "storage").path("../outside.txt")


async def test_save_upload_returns_bytes_written(tmp_path):
    storage = LocalStorage(tmp_path)
    upload = UploadFile(io.BytesIO(b"x" * 10))
    size = await storage.save_upload("meetings/1/original.wav", upload, max_bytes=100)
    assert size == 10
    assert storage.path("meetings/1/original.wav").read_bytes() == b"x" * 10


async def test_oversized_upload_leaves_no_file(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(UploadTooLargeError):
        await storage.save_upload(
            "meetings/1/original.wav", UploadFile(io.BytesIO(b"x" * 101)), max_bytes=100
        )
    assert not storage.path("meetings/1/original.wav").exists()


def test_delete_prefix_removes_the_meeting_folder(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.path("meetings/1/a.wav").write_bytes(b"1")
    storage.path("meetings/2/a.wav").write_bytes(b"2")
    storage.delete_prefix("meetings/1")
    assert not storage.path("meetings/1/a.wav").exists()
    assert storage.path("meetings/2/a.wav").exists()
