"""영상 저장소(파일 배치·삭제·경로 검사·임시 파일 정리)와 SYS-01 상태 확인을 검증."""

import os
import time
import uuid

import pytest

from app.integrations import storage
from app.integrations.storage import (
    TEMP_PREFIX,
    LocalVideoStorage,
    StoragePathError,
    check_video_storage_access,
)


def test_commit_health_check_and_delete_preserve_existing_video(tmp_path):
    root = tmp_path / "videos"
    root.mkdir()
    existing = root / "existing.mp4"
    existing.write_bytes(b"existing video")
    videos = LocalVideoStorage(root)
    payload = b"uploaded video" * 100_000
    temp = videos.temp_file(".mp4")
    temp.write_bytes(payload)
    relative = videos.new_relative_path(uuid.uuid4(), ".mp4")
    path = videos.commit(temp, relative)
    assert path.parent == root and path.suffix == ".mp4" and "/" not in relative
    assert path.read_bytes() == payload and not temp.exists()
    check_video_storage_access(root)
    assert set(root.iterdir()) == {existing, path}
    assert videos.delete(relative) is True
    assert videos.delete(relative) is False
    assert list(root.iterdir()) == [existing]
    assert existing.read_bytes() == b"existing video"


def test_commit_refuses_to_overwrite_existing_file(tmp_path):
    videos = LocalVideoStorage(tmp_path)
    existing = tmp_path / "taken.mp4"
    existing.write_bytes(b"existing video")
    temp = videos.temp_file(".mp4")
    temp.write_bytes(b"new video")
    with pytest.raises(StoragePathError):
        videos.commit(temp, "taken.mp4")
    assert existing.read_bytes() == b"existing video"


def test_failed_file_placement_preserves_existing_video(tmp_path, monkeypatch):
    existing = tmp_path / "existing.mp4"
    existing.write_bytes(b"existing video")
    videos = LocalVideoStorage(tmp_path)
    temp = videos.temp_file(".mp4")
    temp.write_bytes(b"uploaded video")

    def deny_replace(source, destination):
        raise OSError("storage unavailable")

    monkeypatch.setattr(storage.os, "replace", deny_replace)
    with pytest.raises(OSError):
        videos.commit(temp, "new.mp4")
    assert not (tmp_path / "new.mp4").exists()
    assert existing.read_bytes() == b"existing video"


@pytest.mark.parametrize(
    "path",
    ["../outside.mp4", "/outside.mp4", "C:/outside.mp4", "..\\outside.mp4", "a/../../x", ""],
)
def test_paths_outside_storage_root_are_rejected(tmp_path, path):
    root = tmp_path / "videos"
    root.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside video")
    with pytest.raises(ValueError):
        LocalVideoStorage(root).delete(path)
    with pytest.raises(StoragePathError):
        LocalVideoStorage(root).resolve_path(path)
    assert outside.read_bytes() == b"outside video"


def test_symlink_escape_is_rejected(tmp_path):
    root = tmp_path / "videos"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.mp4").write_bytes(b"x")
    root.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(StoragePathError):
        LocalVideoStorage(root).resolve_path("link/secret.mp4")


def test_cleanup_removes_only_stale_temporary_files(tmp_path):
    videos = LocalVideoStorage(tmp_path)
    stale = videos.temp_file(".upload")
    stale.write_bytes(b"partial")
    old = time.time() - 7200
    os.utime(stale, (old, old))
    fresh = videos.temp_file(".upload")
    fresh.write_bytes(b"in progress")
    video = tmp_path / "kept.mp4"
    video.write_bytes(b"video")
    os.utime(video, (old, old))
    assert videos.cleanup_stale_temp() == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([fresh.name, "kept.mp4"])
    assert fresh.name.startswith(TEMP_PREFIX)


def test_cleanup_without_root_is_noop(tmp_path):
    assert LocalVideoStorage(tmp_path / "missing").cleanup_stale_temp() == 0
    assert not (tmp_path / "missing").exists()
