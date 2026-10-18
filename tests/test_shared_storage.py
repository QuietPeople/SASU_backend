"""영상 저장과 SYS-01 상태 확인이 같은 저장소에서 함께 동작하는지 검증."""

from io import BytesIO

import pytest

from app.integrations import storage
from app.integrations.storage import EmptyUploadError, LocalVideoStorage, check_video_storage_access


def test_save_health_check_and_delete_preserve_existing_video(tmp_path):
    root = tmp_path / "videos"
    root.mkdir()
    existing = root / "existing.mp4"
    existing.write_bytes(b"existing video")
    videos = LocalVideoStorage(root)
    payload = b"uploaded video" * 100_000
    saved = videos.save(BytesIO(payload))
    path = videos.resolve_path(saved.relative_path)
    assert path.parent == root and path.suffix == ".mp4"
    assert saved.size_bytes == len(payload) and path.read_bytes() == payload
    check_video_storage_access(root)
    assert set(root.iterdir()) == {existing, path}
    assert existing.read_bytes() == b"existing video"
    videos.delete(saved.relative_path)
    assert list(root.iterdir()) == [existing]


def test_empty_upload_does_not_leave_temporary_or_final_file(tmp_path):
    with pytest.raises(EmptyUploadError):
        LocalVideoStorage(tmp_path).save(BytesIO())
    assert list(tmp_path.iterdir()) == []


def test_failed_file_placement_preserves_existing_video_and_cleans_partial_upload(
    tmp_path, monkeypatch
):
    existing = tmp_path / "existing.mp4"
    existing.write_bytes(b"existing video")

    def deny_replace(source, destination):
        raise OSError("storage unavailable")

    monkeypatch.setattr(storage.os, "replace", deny_replace)
    with pytest.raises(OSError):
        LocalVideoStorage(tmp_path).save(BytesIO(b"uploaded video"))
    assert list(tmp_path.iterdir()) == [existing]
    assert existing.read_bytes() == b"existing video"


@pytest.mark.parametrize(
    "path", ["../outside.mp4", "/outside.mp4", "C:/outside.mp4", "..\\outside.mp4"]
)
def test_delete_rejects_paths_outside_storage_root(tmp_path, path):
    root = tmp_path / "videos"
    root.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside video")
    with pytest.raises(ValueError):
        LocalVideoStorage(root).delete(path)
    assert outside.read_bytes() == b"outside video"
