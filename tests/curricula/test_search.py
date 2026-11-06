from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.modules.curricula import repository
from app.modules.curricula.schemas import CurriculumListQuery


def create_series(ctx, title, description=None, steps=(), *, day=1):
    curriculum_id = repository.create_curriculum(ctx.session, title, description)
    repository.replace_steps(ctx.session, curriculum_id, list(steps))
    ctx.session.execute(
        text("UPDATE sasu.curricula SET created_at=:created WHERE curriculum_id=:id"),
        {"created": datetime(2026, 1, day, tzinfo=UTC), "id": curriculum_id},
    )
    ctx.session.commit()
    return curriculum_id


def list_series(ctx, *, actor=None, **query):
    return ctx.client.get(
        "/api/curriculums",
        params={"view": "editor", "q": ctx.prefix, **query},
        headers={"X-Actor-Id": str(ctx.admin if actor is None else actor)},
    )


def test_query_trims_search_preserves_defaults_and_rejects_invalid_fields():
    query = CurriculumListQuery(q="  Excel  ")
    assert (query.q, query.page, query.size, query.view) == ("Excel", 1, 20, "learner")
    assert CurriculumListQuery(q="   ").q == ""
    assert CurriculumListQuery(q="가" * 200).q == "가" * 200
    for data in ({"q": "가" * 201}, {"unknown": 1}, {"page": 0}, {"size": 101}):
        with pytest.raises(ValidationError):
            CurriculumListQuery(**data)


def test_title_description_search_and_editor_pagination(search_context, monkeypatch):
    ctx = search_context
    title_match = create_series(ctx, f"{ctx.prefix} Excel 기초", steps=[ctx.available])
    description_match = create_series(
        ctx, "제목으로는 검색되지 않는 과정", f"{ctx.prefix} EXCEL 설명", day=2
    )
    create_series(ctx, f"{ctx.prefix} 다른 주제", day=3)
    original = repository.list_step_states
    requested = []

    def scoped_states(session, curriculum_ids, user_id):
        requested.append(curriculum_ids)
        return original(session, curriculum_ids, user_id)

    monkeypatch.setattr(repository, "list_step_states", scoped_states)
    query = {"q": f"  {ctx.prefix} eXcEl  ", "size": 1}
    first = list_series(ctx, **query)
    assert first.status_code == 200, first.text
    data = first.json()
    assert (data["total"], data["page"], data["size"], data["has_next"]) == (2, 1, 1, True)
    assert [item["curriculum_id"] for item in data["items"]] == [description_match]
    assert data["items"][0]["progress_percent"] is None
    assert requested == [[description_match]]
    second = list_series(ctx, page=2, **query).json()
    assert second["total"] == 2 and second["has_next"] is False
    assert [item["curriculum_id"] for item in second["items"]] == [title_match]
    assert second["items"][0]["available_steps"] == 1
    assert requested[-1] == [title_match]
    for page in (3, 10**30):
        beyond = list_series(ctx, page=page, **query)
        assert beyond.status_code == 200, beyond.text
        assert beyond.json()["total"] == 2 and beyond.json()["items"] == []
        assert beyond.json()["has_next"] is False
        assert requested[-1] == []


@pytest.mark.parametrize("literal", ["%", "_", "\\", "' OR 1=1 --", "/"])
def test_search_treats_special_characters_literally(search_context, literal):
    ctx = search_context
    expected = create_series(ctx, "검색 대상", f"{ctx.prefix} {literal}")
    create_series(ctx, f"{ctx.prefix} X", None)
    response = list_series(ctx, q=f"{ctx.prefix} {literal}")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert [item["curriculum_id"] for item in response.json()["items"]] == [expected]


def test_learner_search_keeps_visibility_progress_and_stable_order(search_context, monkeypatch):
    ctx = search_context
    first = create_series(ctx, f"{ctx.prefix} 첫 과정", steps=[ctx.available, ctx.draft])
    second = create_series(ctx, "두 번째 과정", ctx.prefix, steps=[ctx.available])
    create_series(ctx, f"{ctx.prefix} 빈 과정")
    create_series(ctx, f"{ctx.prefix} 비공개", steps=[ctx.draft])
    create_series(ctx, f"{ctx.prefix} 파일 없음", steps=[ctx.missing])
    unrelated = create_series(ctx, "검색과 관계없는 과정", steps=[ctx.available])
    original = repository.list_step_states

    def matching_states(session, curriculum_ids, user_id):
        assert unrelated not in curriculum_ids
        return original(session, curriculum_ids, user_id)

    monkeypatch.setattr(repository, "list_step_states", matching_states)
    result = list_series(ctx, view="learner", actor=ctx.learner, size=1)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["total"] == 2 and data["has_next"] is True
    summary = data["items"][0]
    assert summary["curriculum_id"] == first
    assert (summary["total_steps"], summary["available_steps"]) == (2, 1)
    assert (summary["completed_steps"], summary["progress_percent"]) == (0, 0.0)
    detail = ctx.client.get(f"/api/curriculums/{first}", headers={"X-Actor-Id": str(ctx.learner)})
    assert detail.status_code == 200, detail.text
    assert summary == detail.json()["summary"]
    next_page = list_series(ctx, view="learner", actor=ctx.learner, size=1, page=2).json()
    assert next_page["total"] == 2 and next_page["has_next"] is False
    assert [item["curriculum_id"] for item in next_page["items"]] == [second]
    editor = list_series(ctx).json()
    assert editor["total"] == 5 and len(editor["items"]) == 5
    with_target = list_series(ctx, user_id=ctx.learner).json()
    assert with_target["items"][0]["progress_percent"] == 0.0


def test_blank_no_match_validation_and_access(search_context):
    ctx = search_context
    blank = list_series(ctx, q="   ")
    default = ctx.client.get("/api/curriculums?view=editor", headers={"X-Actor-Id": str(ctx.admin)})
    assert blank.status_code == default.status_code == 200
    assert blank.json() == default.json()
    for view in ("learner", "editor"):
        no_match = list_series(ctx, view=view).json()
        assert (no_match["total"], no_match["has_next"], no_match["items"]) == (0, False, [])
    invalid = list_series(ctx, q="가" * 201)
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "VALIDATION_ERROR"
    assert list_series(ctx, actor=ctx.learner).status_code == 403
    assert list_series(ctx, view="learner", actor=ctx.learner, user_id=ctx.other).status_code == 404
    assert list_series(ctx, user_id=2**63 - 1).status_code == 404
    assert list_series(ctx, unknown=1).status_code == 422
