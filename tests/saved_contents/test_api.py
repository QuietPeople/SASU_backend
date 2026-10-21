from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.contents.models import Content, ContentStatus, VideoAsset
from app.modules.saved_contents import repository, temporary_bridge
from app.modules.saved_contents.tables import saved_contents
from app.modules.users.models import User, UserRole


def relations(ctx):
    with ctx.session.begin():
        return (
            ctx.session.execute(
                select(saved_contents)
                .where(saved_contents.c.user_id.in_([ctx.learner, ctx.other]))
                .order_by(saved_contents.c.user_id, saved_contents.c.content_id)
            )
            .mappings()
            .all()
        )


def test_save_repeat_list_detail_and_unsave(api_context):
    ctx = api_context
    response = ctx.client.put(ctx.path, headers=ctx.headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"content_id": ctx.contents[0], "saved": True}
    first_time = datetime(2020, 1, 1, tzinfo=UTC)
    with ctx.session.begin():
        ctx.session.execute(
            update(saved_contents)
            .where(saved_contents.c.user_id == ctx.learner)
            .values(created_at=first_time)
        )
    assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200
    assert len(relations(ctx)) == 1 and relations(ctx)[0]["created_at"] == first_time
    listing = ctx.client.get(ctx.list_path, headers={"X-Actor-Id": str(ctx.learner)})
    assert listing.status_code == 200, listing.text
    data = listing.json()
    assert (data["total"], data["has_next"]) == (1, False)
    assert data["items"][0]["saved_at"] == "2020-01-01T00:00:00Z"
    summary = data["items"][0]["content"]
    assert summary["saved"] is True and summary["content_id"] == ctx.contents[0]
    detail = ctx.client.get(f"/api/contents/{ctx.contents[0]}", headers=ctx.headers)
    assert detail.status_code == 200 and detail.json()["content"] == summary
    for _ in range(2):
        response = ctx.client.delete(ctx.path, headers=ctx.headers)
        assert response.status_code == 200 and response.json()["saved"] is False
    assert ctx.client.get(ctx.list_path, headers=ctx.headers).json()["items"] == []
    assert (
        ctx.client.get(f"/api/contents/{ctx.contents[0]}", headers=ctx.headers).json()["content"][
            "saved"
        ]
        is False
    )


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize("actor,status", [("admin", 403), ("other", 404), ("missing", 404)])
def test_write_access(api_context, method, actor, status):
    ctx = api_context
    actor_id = getattr(ctx, actor) if actor != "missing" else 2**63 - 1
    response = ctx.client.request(
        method, ctx.path, headers={**ctx.headers, "X-Actor-Id": str(actor_id)}
    )
    assert response.status_code == status, response.text
    assert relations(ctx) == []


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_missing_content_and_future_generation(api_context, method):
    ctx = api_context
    response = ctx.client.request(
        method, f"/api/users/{ctx.learner}/contents/{2**63 - 1}/saved", headers=ctx.headers
    )
    assert response.status_code == 404 and response.json()["detail"]["code"] == "CONTENT_NOT_FOUND"
    response = ctx.client.request(
        method, ctx.path, headers={**ctx.headers, "X-Record-Generation": "1"}
    )
    assert (
        response.status_code == 409
        and response.json()["detail"]["code"] == "RECORD_GENERATION_MISMATCH"
    )
    assert relations(ctx) == []


def test_user_without_settings_is_not_created_automatically(api_context):
    ctx = api_context
    with ctx.session.begin():
        user = User(
            username=f"save_{uuid4().hex[:12]}", display_name="설정 없음", role=UserRole.LEARNER
        )
        ctx.session.add(user)
        ctx.session.flush()
        user_id = user.user_id
    headers = {**ctx.headers, "X-Actor-Id": str(user_id)}
    response = ctx.client.put(
        f"/api/users/{user_id}/contents/{ctx.contents[0]}/saved", headers=headers
    )
    assert response.status_code == 404 and response.json()["detail"]["code"] == "USER_NOT_FOUND"
    assert (
        ctx.client.get(f"/api/users/{user_id}/saved-contents", headers=headers).status_code == 404
    )
    with ctx.session.begin():
        assert (
            ctx.session.scalar(
                text("SELECT count(*) FROM sasu.user_settings WHERE user_id=:id"), {"id": user_id}
            )
            == 0
        )


def test_unpublished_content_can_only_be_unsaved(api_context):
    ctx = api_context
    assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200
    with ctx.session.begin():
        ctx.session.get(Content, ctx.contents[0]).status = ContentStatus.DRAFT
    response = ctx.client.put(ctx.path, headers=ctx.headers)
    assert response.status_code == 404
    assert ctx.client.get(ctx.list_path, headers=ctx.headers).json()["total"] == 0
    assert len(relations(ctx)) == 1
    assert ctx.client.delete(ctx.path, headers=ctx.headers).status_code == 200
    assert relations(ctx) == []


def test_list_filters_orders_and_pages_before_counting(api_context):
    ctx = api_context
    first_time = datetime(2020, 1, 1, tzinfo=UTC)
    for content_id in ctx.contents:
        assert (
            ctx.client.put(
                f"/api/users/{ctx.learner}/contents/{content_id}/saved", headers=ctx.headers
            ).status_code
            == 200
        )
    with ctx.session.begin():
        for i, content_id in enumerate(ctx.contents):
            ctx.session.execute(
                update(saved_contents)
                .where(
                    saved_contents.c.user_id == ctx.learner,
                    saved_contents.c.content_id == content_id,
                )
                .values(created_at=first_time + timedelta(days=i))
            )
    response = ctx.client.get(ctx.list_path + "?size=1", headers=ctx.headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["total"], data["has_next"]) == (3, True)
    assert data["items"][0]["content"]["content_id"] == ctx.contents[2]
    data = ctx.client.get(
        ctx.list_path, params={"category_id": ctx.categories[0]}, headers=ctx.headers
    ).json()
    assert [item["content"]["content_id"] for item in data["items"]] == ctx.contents[1::-1]
    with ctx.session.begin():
        ctx.session.get(Content, ctx.contents[2]).status = ContentStatus.DRAFT
        content = ctx.session.get(Content, ctx.contents[1])
        video = ctx.session.get(VideoAsset, content.video_asset_id)
        ctx.storage.resolve_path(video.storage_path).unlink()
    before = relations(ctx)
    data = ctx.client.get(ctx.list_path + "?size=1", headers=ctx.headers).json()
    assert data["total"] == 1 and data["has_next"] is False
    assert [item["content"]["content_id"] for item in data["items"]] == [ctx.contents[0]]
    beyond = ctx.client.get(ctx.list_path + "?size=1&page=2", headers=ctx.headers).json()
    assert beyond["total"] == 1 and beyond["items"] == []
    assert relations(ctx) == before


def test_list_access_category_and_empty_result(api_context):
    ctx = api_context
    response = ctx.client.get(ctx.list_path, headers={"X-Actor-Id": str(ctx.admin)})
    assert response.status_code == 200 and response.json()["items"] == []
    assert ctx.client.get(ctx.list_path, headers={"X-Actor-Id": str(ctx.other)}).status_code == 404
    assert (
        ctx.client.get(
            f"/api/users/{ctx.admin}/saved-contents", headers={"X-Actor-Id": str(ctx.admin)}
        ).status_code
        == 404
    )
    response = ctx.client.get(ctx.list_path, params={"category_id": 2**63 - 1}, headers=ctx.headers)
    assert response.status_code == 404 and response.json()["detail"]["code"] == "CATEGORY_NOT_FOUND"


def test_reset_rejects_old_writes_and_keeps_new_save(api_context):
    ctx = api_context
    assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200
    response = ctx.client.post(
        f"/api/users/{ctx.learner}/test-records/reset",
        headers={"X-Actor-Id": str(ctx.admin)},
        json={"confirm": True, "expected_record_generation": 0},
    )
    assert response.status_code == 200, response.text
    assert response.json()["record_generation"] == 1
    assert response.json()["deleted_counts"]["saved_contents"] == 1
    assert relations(ctx) == []
    current = {**ctx.headers, "X-Record-Generation": "1"}
    assert ctx.client.put(ctx.path, headers=current).status_code == 200
    before = relations(ctx)
    for method in ("PUT", "DELETE"):
        assert ctx.client.request(method, ctx.path, headers=ctx.headers).status_code == 409
        assert relations(ctx) == before
    assert before[0]["learning_epoch"] == 2


def test_shared_lookup_is_scoped_and_read_only(api_context):
    ctx = api_context
    assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200
    with ctx.session.begin():
        repository.insert_saved_content(ctx.session, ctx.other, ctx.contents[1], 1)
        assert repository.get_saved_content_ids(
            ctx.session, ctx.learner, [*ctx.contents, ctx.contents[0]]
        ) == {ctx.contents[0]}
        assert repository.get_saved_content_ids(ctx.session, ctx.other, ctx.contents) == {
            ctx.contents[1]
        }
        assert repository.get_saved_content_ids(ctx.session, ctx.learner, []) == set()


def test_unsave_preserves_like_other_user_and_content(api_context):
    ctx = api_context
    assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200
    like_path = f"/api/users/{ctx.learner}/contents/{ctx.contents[0]}/like"
    assert ctx.client.put(like_path, headers=ctx.headers).status_code == 200
    other_path = f"/api/users/{ctx.other}/contents/{ctx.contents[0]}/saved"
    other_headers = {**ctx.headers, "X-Actor-Id": str(ctx.other)}
    assert ctx.client.put(other_path, headers=other_headers).status_code == 200
    summary = ctx.client.get(ctx.list_path, headers=ctx.headers).json()["items"][0]["content"]
    assert summary["liked"] is True and summary["like_count"] == 1
    assert ctx.client.delete(ctx.path, headers=ctx.headers).status_code == 200
    rows = relations(ctx)
    assert len(rows) == 1 and rows[0]["user_id"] == ctx.other
    response = ctx.client.get(f"/api/contents/{ctx.contents[0]}", headers=ctx.headers)
    assert response.status_code == 200
    assert response.json()["content"]["liked"] is True
    assert response.json()["content"]["saved"] is False


def test_unavailable_external_lookup_is_not_a_successful_empty_list(api_context, monkeypatch):
    ctx = api_context
    assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200
    before = relations(ctx)

    def fail(*args):
        raise SQLAlchemyError("공개하면 안 되는 내부 조회 오류")

    monkeypatch.setattr(temporary_bridge, "load_saved_presentations", fail)
    response = ctx.client.get(ctx.list_path, headers=ctx.headers)
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_ERROR"
    assert "내부 조회 오류" not in response.text
    assert relations(ctx) == before


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_commit_failure_rolls_back_and_allows_retry(api_context, method):
    ctx = api_context
    if method == "DELETE":
        assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200
    before = relations(ctx)

    def fail_commit(session):
        raise SQLAlchemyError("공개하면 안 되는 커밋 오류")

    event.listen(Session, "before_commit", fail_commit)
    try:
        response = ctx.client.request(method, ctx.path, headers=ctx.headers)
    finally:
        event.remove(Session, "before_commit", fail_commit)
    assert response.status_code == 500
    assert relations(ctx) == before
    assert ctx.client.request(method, ctx.path, headers=ctx.headers).status_code == 200
