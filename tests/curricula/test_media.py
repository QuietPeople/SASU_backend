from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.modules.curricula.service import make_step


@pytest.fixture
def media_row():
    root = get_settings().video_storage_root
    root.mkdir()
    (root / "video.mp4").write_bytes(b"video")
    return {
        "content_id": 1,
        "position": 2,
        "status": "PUBLISHED",
        "storage_path": "video.mp4",
        "video_asset_id": uuid4(),
        "title": "콘텐츠",
        "category_id": 1,
        "category_name": "분류",
        "tags": [],
        "duration_seconds": 1.2,
        "view_count": 0,
        "like_count": 0,
        "liked": True,
        "saved": False,
        "watched": True,
        "correct": True,
        "has_quiz": True,
    }


@pytest.mark.parametrize("status", ["DRAFT", "PUBLISHED"])
@pytest.mark.parametrize("view", ["learner", "editor"])
def test_step_preserves_visibility_and_preview_url(media_row, status, view):
    media_row["status"] = status
    user_id = 2 if view == "learner" else None
    step = make_step(media_row, user_id, view, actor_id=9)
    assert step.available is (status == "PUBLISHED")
    assert step.content_id == step.curriculum_content_id == 1
    assert step.step_order == 2
    assert step.watch_completed is (True if user_id else None)
    if status == "DRAFT" and view == "learner":
        assert step.content is None
        return
    url = urlsplit(step.content.video_url)
    assert url.path == "/api/contents/1/video"
    query = {"revision": [str(media_row["video_asset_id"])]}
    if view == "editor":
        query.update(preview=["true"], actor_id=["9"])
    assert parse_qs(url.query) == query
    assert step.content.liked is (True if user_id else None)


def test_missing_video_preserves_unavailable_step(media_row):
    media_row["storage_path"] = "missing.mp4"
    step = make_step(media_row, 2, "learner", actor_id=2)
    assert step.available is False and step.content is None
    assert step.content_id == 1 and step.step_order == 2
    assert step.watch_completed is True


@pytest.mark.parametrize("kind", ["parent", "absolute", "windows", "backslash", "symlink"])
def test_unsafe_video_cannot_be_exposed_as_available_step(media_row, tmp_path, kind):
    root = get_settings().video_storage_root
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside video")
    link = root / "link.mp4"
    link.symlink_to(outside)
    media_row["storage_path"] = {
        "parent": "../outside.mp4",
        "absolute": str(outside),
        "windows": "C:/outside.mp4",
        "backslash": "..\\outside.mp4",
        "symlink": "link.mp4",
    }[kind]
    step = make_step(media_row, 2, "learner", actor_id=2)
    assert step.available is False and step.content is None
    assert outside.read_bytes() == b"outside video"
