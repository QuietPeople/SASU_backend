from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.modules.contents.schemas import ContentSummary
from app.modules.saved_contents.schemas import SavedContentsQuery, SavedItem, SaveState


def item(content_id):
    return SavedItem(
        content=ContentSummary(
            content_id=content_id,
            title="저장한 콘텐츠",
            category={"category_id": 1, "name": "엑셀"},
            tags=[],
            video_duration=4.5,
            video_url=f"/api/contents/{content_id}/video",
            media_revision="media-r1",
            view_count=0,
            like_count=0,
            liked=False,
            saved=True,
            watch_completed=False,
            has_quiz=False,
            status="PUBLISHED",
        ),
        saved_at=datetime(2026, 10, 21, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    "data",
    [
        {"page": 0},
        {"page": -1},
        {"size": 0},
        {"size": 101},
        {"category_id": 0},
        {"category_id": 2**63},
        {"unknown": 1},
    ],
)
def test_invalid_query(data):
    with pytest.raises(ValidationError):
        SavedContentsQuery.model_validate(data)


def test_query_defaults_and_category_conversion():
    query = SavedContentsQuery.model_validate({"category_id": "1"})
    assert (query.page, query.size, query.category_id) == (1, 20, 1)


@pytest.mark.parametrize("content_id", [0, -1, 2**63])
def test_invalid_state_content_id(content_id):
    with pytest.raises(ValidationError):
        SaveState(content_id=content_id, saved=True)


def test_state_and_saved_item_contract():
    assert SaveState(content_id=1, saved=False).model_dump() == {"content_id": 1, "saved": False}
    value = item(1)
    assert value.model_dump(mode="json")["saved_at"] == "2026-10-21T00:00:00Z"
    assert value.content.saved is True
    data = value.model_dump()
    data["saved_at"] = datetime(2026, 10, 21)
    with pytest.raises(ValidationError):
        SavedItem.model_validate(data)
    with pytest.raises(ValidationError):
        SaveState(content_id=1, saved=True, other="사용하지 않는 필드")
