from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.modules.contents.schemas import ContentSummary
from app.modules.saved_contents.schemas import SavedContentsQuery, SavedItem, SaveState
from app.modules.saved_contents.service import paginate_saved_items


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


@pytest.mark.parametrize(
    "page,size,ids,has_next",
    [(1, 2, [3, 1], True), (2, 2, [2], False), (3, 2, [], False), (1, 3, [3, 1, 2], False)],
)
def test_pagination_preserves_supplied_order(page, size, ids, has_next):
    eligible = [item(i) for i in [3, 1, 2]]
    result = paginate_saved_items(eligible, SavedContentsQuery(page=page, size=size))
    assert [value.content.content_id for value in result.items] == ids
    assert (result.page, result.size, result.total, result.has_next) == (page, size, 3, has_next)
    assert [value.content.content_id for value in eligible] == [3, 1, 2]


def test_total_uses_only_final_eligible_items():
    eligible = [item(i) for i in [5, 2]]
    result = paginate_saved_items(eligible, SavedContentsQuery(size=1))
    assert result.total == 2 and result.has_next is True
    assert [value.content.content_id for value in result.items] == [5]
    empty = paginate_saved_items([], SavedContentsQuery())
    assert empty.total == 0 and empty.has_next is False and empty.items == []
