from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.integrations.storage import LocalVideoStorage
from app.modules.contents.models import Content, VideoAsset
from app.modules.saved_contents.repository import SavedCandidate
from app.modules.saved_contents.service import filter_playable_candidates


def candidate(content_id, path="video.mp4", **changes):
    values = dict(
        storage_path=path,
        original_name="video.mp4",
        size_bytes=5,
        mime_type="video/mp4",
        duration_seconds=Decimal("4.500"),
    )
    values.update(changes)
    return SavedCandidate(
        content=Content(content_id=content_id),
        video=VideoAsset(**values),
        saved_at=datetime(2026, 10, 21, tzinfo=UTC),
    )


def test_filters_missing_files_before_pagination_without_reordering(tmp_path):
    storage = LocalVideoStorage(tmp_path)
    (tmp_path / "video.mp4").write_bytes(b"video")
    candidates = [candidate(3), candidate(1, "missing.mp4"), candidate(2)]
    before = list(candidates)
    result = filter_playable_candidates(candidates, storage)
    assert [item.content.content_id for item in result] == [3, 2]
    assert candidates == before
    assert (tmp_path / "video.mp4").read_bytes() == b"video"


@pytest.mark.parametrize(
    "changes",
    [
        {"storage_path": "../outside.mp4"},
        {"storage_path": "/outside.mp4"},
        {"storage_path": "missing.mp4"},
        {"size_bytes": 4},
        {"size_bytes": 0},
        {"mime_type": "video/quicktime"},
        {"duration_seconds": Decimal("0")},
        {"duration_seconds": Decimal("NaN")},
        {"duration_seconds": Decimal("Infinity")},
    ],
)
def test_invalid_video_is_excluded(tmp_path, changes):
    (tmp_path / "video.mp4").write_bytes(b"video")
    assert filter_playable_candidates([candidate(1, **changes)], LocalVideoStorage(tmp_path)) == []


def test_directory_symlink_and_unlinked_video_are_excluded(tmp_path):
    root = tmp_path / "videos"
    root.mkdir()
    (root / "directory.mp4").mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")
    (root / "symlink.mp4").symlink_to(outside)
    missing_asset = SavedCandidate(Content(content_id=1), None, datetime.now(UTC))
    assert (
        filter_playable_candidates(
            [missing_asset, candidate(2, "directory.mp4"), candidate(3, "symlink.mp4")],
            LocalVideoStorage(root),
        )
        == []
    )
