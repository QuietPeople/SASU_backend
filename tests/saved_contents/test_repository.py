from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from app.modules.contents.models import Content
from app.modules.saved_contents import repository
from app.modules.saved_contents.tables import saved_contents


def _relations(session):
    return (
        session.execute(
            select(saved_contents).order_by(saved_contents.c.user_id, saved_contents.c.content_id)
        )
        .mappings()
        .all()
    )


def test_repeated_save_preserves_first_time(context):
    ctx = context
    first_time = datetime(2020, 1, 1, tzinfo=UTC)
    with ctx.session.begin():
        repository.insert_saved_content(ctx.session, ctx.learner, ctx.contents[0], 1)
        ctx.session.execute(
            update(saved_contents)
            .where(saved_contents.c.user_id == ctx.learner)
            .values(created_at=first_time)
        )
        repository.insert_saved_content(ctx.session, ctx.learner, ctx.contents[0], 1)
        rows = (
            ctx.session.execute(
                select(saved_contents).where(saved_contents.c.user_id == ctx.learner)
            )
            .mappings()
            .all()
        )
        assert len(rows) == 1
        assert rows[0]["created_at"] == first_time
        assert rows[0]["learning_epoch"] == 1


def test_repeated_delete_preserves_other_user_and_content(context):
    ctx = context
    with ctx.session.begin():
        repository.insert_saved_content(ctx.session, ctx.learner, ctx.contents[0], 1)
        repository.insert_saved_content(ctx.session, ctx.other, ctx.contents[0], 1)
        repository.insert_saved_content(ctx.session, ctx.learner, ctx.contents[1], 1)
        repository.delete_saved_content(ctx.session, ctx.learner, ctx.contents[0])
        repository.delete_saved_content(ctx.session, ctx.learner, ctx.contents[0])
        rows = ctx.session.execute(
            select(saved_contents.c.user_id, saved_contents.c.content_id).where(
                saved_contents.c.user_id.in_([ctx.learner, ctx.other])
            )
        ).all()
        assert set(rows) == {(ctx.other, ctx.contents[0]), (ctx.learner, ctx.contents[1])}
        assert ctx.session.get(Content, ctx.contents[0]) is not None


def test_delete_can_remove_existing_draft_relation(context):
    ctx = context
    with ctx.session.begin():
        # 공개 여부 검사는 서비스 책임이다. 저장소의 삭제는 비공개 관계도 처리해야 한다.
        repository.insert_saved_content(ctx.session, ctx.learner, ctx.draft, 1)
        repository.delete_saved_content(ctx.session, ctx.learner, ctx.draft)
        assert (
            ctx.session.scalar(
                select(func.count())
                .select_from(saved_contents)
                .where(saved_contents.c.user_id == ctx.learner)
            )
            == 0
        )


def test_candidate_order_category_and_user_isolation(context):
    ctx = context
    first_time = datetime(2026, 1, 1, tzinfo=UTC)
    with ctx.session.begin():
        for content_id in [*ctx.contents, ctx.draft]:
            repository.insert_saved_content(ctx.session, ctx.learner, content_id, 1)
            ctx.session.execute(
                update(saved_contents)
                .where(
                    saved_contents.c.user_id == ctx.learner,
                    saved_contents.c.content_id == content_id,
                )
                .values(created_at=first_time + timedelta(days=content_id == ctx.contents[2]))
            )
        repository.insert_saved_content(ctx.session, ctx.other, ctx.contents[1], 1)

        before = _relations(ctx.session)
        rows = repository.list_saved_candidates(ctx.session, ctx.learner)
        assert [row.content.content_id for row in rows] == [
            ctx.contents[2],
            ctx.contents[0],
            ctx.contents[1],
        ]
        assert rows[0].saved_at == first_time + timedelta(days=1)
        assert all(row.video.video_asset_id == row.content.video_asset_id for row in rows)
        filtered = repository.list_saved_candidates(
            ctx.session, ctx.learner, category_id=ctx.categories[0]
        )
        assert [row.content.content_id for row in filtered] == ctx.contents[:2]
        other = repository.list_saved_candidates(ctx.session, ctx.other)
        assert [row.content.content_id for row in other] == [ctx.contents[1]]
        assert (
            repository.list_saved_candidates(ctx.session, ctx.other, category_id=ctx.categories[1])
            == []
        )
        assert _relations(ctx.session) == before


def test_empty_candidates(context):
    assert repository.list_saved_candidates(context.session, context.learner) == []


def test_repository_writes_remain_in_callers_transaction(context):
    ctx = context
    with pytest.raises(RuntimeError, match="취소"), ctx.session.begin():
        repository.insert_saved_content(ctx.session, ctx.learner, ctx.contents[0], 1)
        raise RuntimeError("취소")
    with ctx.session.begin():
        assert repository.list_saved_candidates(ctx.session, ctx.learner) == []
        repository.insert_saved_content(ctx.session, ctx.learner, ctx.contents[0], 1)
    with pytest.raises(RuntimeError, match="취소"), ctx.session.begin():
        repository.delete_saved_content(ctx.session, ctx.learner, ctx.contents[0])
        raise RuntimeError("취소")
    assert [
        row.content.content_id for row in repository.list_saved_candidates(ctx.session, ctx.learner)
    ] == [ctx.contents[0]]


def test_existing_db_trigger_rejects_invalid_epoch(context):
    ctx = context
    with pytest.raises(IntegrityError) as error, ctx.session.begin():
        repository.insert_saved_content(ctx.session, ctx.learner, ctx.contents[0], 2)
    assert error.value.orig.sqlstate == "23514"
    assert repository.list_saved_candidates(ctx.session, ctx.learner) == []


def test_saved_count_view_tracks_relationship_changes(context):
    ctx = context
    statement = text("SELECT saved_count FROM sasu.content_metrics WHERE content_id = :content_id")
    with ctx.session.begin():
        repository.insert_saved_content(ctx.session, ctx.learner, ctx.contents[0], 1)
        repository.insert_saved_content(ctx.session, ctx.other, ctx.contents[0], 1)
        assert ctx.session.scalar(statement, {"content_id": ctx.contents[0]}) == 2
        repository.delete_saved_content(ctx.session, ctx.learner, ctx.contents[0])
        assert ctx.session.scalar(statement, {"content_id": ctx.contents[0]}) == 1
