from io import BytesIO
from uuid import uuid4

import pytest
from alembic.config import Config
from PIL import Image
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from alembic import command
from app.core.config import PROJECT_ROOT, get_settings
from app.integrations.storage import LocalVideoStorage
from app.modules.contents import deletion_repository


def editor(ctx, content_id=None):
    response = ctx.client.get(
        f"/api/contents/{content_id or ctx.content_id}?view=editor", headers=ctx.headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def version(ctx, content_id=None):
    return {"expected_updated_at": editor(ctx, content_id)["updated_at"]}


def remove(ctx, **body):
    return ctx.client.request(
        "DELETE",
        f"/api/contents/{ctx.content_id}",
        headers=ctx.headers,
        json={**version(ctx), "confirm": True, **body},
    )


def scalar(ctx, sql, **params):
    return ctx.database.scalar(text(sql), params)


def seed_history(ctx, index=0, *, correct=False):
    db, rec = ctx.database, ctx.records
    q = rec["questions"][index]
    cid, uid = q["content_id"], rec["learner"]
    db.execute(
        text("""INSERT INTO sasu.watch_records
            (user_id, learning_epoch, content_id, first_played_at, last_watched_at,
             view_counted_at, completed_at) VALUES (:user, 1, :cid, now(), now(), now(), now())"""),
        {"user": uid, "cid": cid},
    )
    for table in ("content_likes", "saved_contents"):
        db.execute(
            text(
                f"INSERT INTO sasu.{table} (user_id, learning_epoch, content_id) "
                "VALUES (:user, 1, :cid)"
            ),
            {"user": uid, "cid": cid},
        )
    attempt, event, retry = uuid4(), uuid4(), uuid4()
    db.execute(
        text("""INSERT INTO sasu.quiz_attempts
            (attempt_id, user_id, learning_epoch, quiz_id, quiz_version_id, context)
            VALUES (:attempt, :user, 1, :quiz, :version, 'VIDEO_END')"""),
        {
            "attempt": attempt,
            "user": uid,
            "quiz": q["question_id"],
            "version": q["question_version_id"],
        },
    )
    db.execute(
        text("""INSERT INTO sasu.learning_events
            (event_id, user_id, learning_epoch, event_type, content_id, quiz_version_id, attempt_id)
            VALUES (:event, :user, 1, 'QUIZ_DISPLAYED', :cid, :version, :attempt)"""),
        {
            "event": event,
            "user": uid,
            "cid": cid,
            "version": q["question_version_id"],
            "attempt": attempt,
        },
    )
    db.execute(
        text("INSERT INTO sasu.event_retry_keys VALUES (:retry, :event)"),
        {"retry": retry, "event": event},
    )
    db.execute(
        text("""INSERT INTO sasu.quiz_responses
            (attempt_id, quiz_version_id, selected_option_id, result)
            VALUES (:attempt, :version, :option, :result)"""),
        {
            "attempt": attempt,
            "version": q["question_version_id"],
            "option": next(o["option_id"] for o in q["options"] if o["is_correct"] == correct),
            "result": "CORRECT" if correct else "WRONG",
        },
    )
    asset = scalar(ctx, "SELECT video_asset_id FROM sasu.contents WHERE content_id=:id", id=cid)
    db.execute(
        text("""INSERT INTO sasu.watch_visits
            (visit_id, user_id, learning_epoch, content_id, video_asset_id, context)
            VALUES (:visit, :user, 1, :cid, :asset, 'FEED')"""),
        {"visit": uuid4(), "user": uid, "cid": cid, "asset": asset},
    )
    db.execute(
        text("UPDATE sasu.user_settings SET last_content_id=:cid WHERE user_id=:user"),
        {"cid": cid, "user": uid},
    )
    db.commit()
    return {"attempt": attempt, "event": event, "retry": retry, "asset": asset}


def series(ctx):
    cid = scalar(ctx, "INSERT INTO sasu.curricula (title) VALUES ('순서') RETURNING curriculum_id")
    for position, q in enumerate(ctx.records["questions"], 1):
        ctx.database.execute(
            text("INSERT INTO sasu.curriculum_items VALUES (:series, :content, :position)"),
            {"series": cid, "content": q["content_id"], "position": position},
        )
    ctx.database.commit()
    return cid


def image(ctx):
    data = BytesIO()
    Image.new("RGB", (8, 8), "red").save(data, format="PNG")
    response = ctx.client.put(
        f"/api/contents/{ctx.content_id}/thumbnail",
        headers=ctx.headers,
        files={"file": ("thumb.png", data.getvalue(), "image/png")},
    )
    assert response.status_code == 204, response.text
    return editor(ctx)["detail"]["content"]["thumbnail_url"]


def test_00_migration_round_trip(postgres_engine):
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    with postgres_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0003_event_retry_keys")
        command.upgrade(config, "head")
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0004_content_control"
        )


@pytest.mark.parametrize("confirmation", [False, None, 1, "true"])
def test_delete_requires_explicit_boolean_confirmation(context, confirmation):
    assert remove(context, confirm=confirmation).status_code == 422
    assert editor(context)["detail"]["content"]["status"] == "PUBLISHED"


def test_permanent_delete_cleans_references_and_reorders_series(context):
    ctx = context
    history = seed_history(ctx)
    image(ctx)
    cur = series(ctx)
    before_version = scalar(
        ctx, "SELECT updated_at FROM sasu.curricula WHERE curriculum_id=:cur", cur=cur
    )
    video = scalar(
        ctx,
        "SELECT storage_path FROM sasu.video_assets WHERE video_asset_id=:asset",
        asset=history["asset"],
    )
    images = list(get_settings().image_storage_root.iterdir())
    assert (get_settings().video_storage_root / video).is_file()
    assert remove(ctx).json() == {"content_id": ctx.content_id, "file_cleanup_pending": False}
    for table in (
        "watch_records",
        "watch_visits",
        "content_likes",
        "saved_contents",
        "quiz_attempts",
        "quiz_responses",
        "wrong_answers",
        "learning_events",
        "event_retry_keys",
        "image_assets",
    ):
        assert scalar(ctx, f"SELECT count(*) FROM sasu.{table}") == 0
    assert scalar(ctx, "SELECT count(*) FROM sasu.quizzes") == 2
    assert scalar(ctx, "SELECT count(*) FROM sasu.quiz_versions") == 2
    assert scalar(ctx, "SELECT count(*) FROM sasu.quiz_options") == 4
    assert scalar(ctx, "SELECT count(*) FROM sasu.contents") == 2
    assert scalar(ctx, "SELECT count(*) FROM sasu.categories") == 1
    assert scalar(ctx, "SELECT count(*) FROM sasu.tags") == 1
    assert scalar(ctx, "SELECT count(*) FROM sasu.app_users") == 4
    assert (
        scalar(
            ctx,
            "SELECT last_content_id FROM sasu.user_settings WHERE user_id=:uid",
            uid=ctx.records["learner"],
        )
        is None
    )
    assert list(
        ctx.database.scalars(
            text("""SELECT position FROM sasu.curriculum_items
        WHERE curriculum_id=:cur ORDER BY position"""),
            {"cur": cur},
        )
    ) == [1, 2]
    assert (
        scalar(ctx, "SELECT updated_at FROM sasu.curricula WHERE curriculum_id=:cur", cur=cur)
        > before_version
    )
    assert not (get_settings().video_storage_root / video).exists()
    assert all(not path.exists() for path in images)
    assert (
        ctx.client.get(
            f"/api/contents/{ctx.content_id}?view=editor", headers=ctx.headers
        ).status_code
        == 404
    )


def test_deletion_preserves_shared_thumbnail(context):
    ctx = context
    image(ctx)
    cur = series(ctx)
    thumbnail = scalar(
        ctx, "SELECT thumbnail_image_id FROM sasu.contents WHERE content_id=:id", id=ctx.content_id
    )
    ctx.database.execute(
        text("""UPDATE sasu.curricula SET thumbnail_image_id=:image WHERE curriculum_id=:cur"""),
        {"image": thumbnail, "cur": cur},
    )
    ctx.database.commit()
    paths = list(get_settings().image_storage_root.iterdir())
    assert remove(ctx).status_code == 200
    assert scalar(ctx, "SELECT count(*) FROM sasu.image_assets") == 1
    assert all(path.is_file() for path in paths)


def test_database_failure_rolls_back_history_and_preserves_files(context, monkeypatch):
    ctx = context
    seed_history(ctx)
    image(ctx)
    original = deletion_repository.delete_owned_rows
    paths = list(get_settings().video_storage_root.iterdir())

    def fail(session, content):
        original(session, content)
        raise OperationalError("forced failure", {}, Exception())

    monkeypatch.setattr(deletion_repository, "delete_owned_rows", fail)
    response = remove(ctx)
    assert response.status_code == 500
    assert scalar(ctx, "SELECT count(*) FROM sasu.quiz_responses") == 1
    assert scalar(ctx, "SELECT count(*) FROM sasu.quiz_options") == 6
    assert all(path.is_file() for path in paths)
    assert editor(ctx)["detail"]["content"]["status"] == "PUBLISHED"


def test_file_cleanup_failure_is_reported_without_restoring_deleted_content(context, monkeypatch):
    ctx = context

    def fail(*args):
        raise PermissionError("locked file")

    monkeypatch.setattr(LocalVideoStorage, "delete", fail)
    response = remove(ctx)
    assert response.status_code == 200, response.text
    assert response.json()["file_cleanup_pending"] is True
    assert (
        scalar(ctx, "SELECT count(*) FROM sasu.contents WHERE content_id=:id", id=ctx.content_id)
        == 0
    )


@pytest.mark.parametrize(
    "table,id_column", [("quiz_versions", "quiz_version_id"), ("quiz_options", "option_id")]
)
@pytest.mark.parametrize("operation", ["DELETE", "UPDATE"])
def test_standalone_quiz_history_changes_remain_forbidden(context, table, id_column, operation):
    ctx = context
    q = ctx.records["questions"][0]
    key = q["question_version_id"] if table == "quiz_versions" else q["options"][0]["option_id"]
    statement = (
        f"DELETE FROM sasu.{table}"
        if operation == "DELETE"
        else (
            f"UPDATE sasu.{table} SET "
            + (
                "question_text=question_text"
                if table == "quiz_versions"
                else "option_text=option_text"
            )
        )
    )
    with pytest.raises(IntegrityError), ctx.database.begin_nested():
        ctx.database.execute(text(statement + f" WHERE {id_column}=:key"), {"key": key})


def test_quiz_parent_cannot_be_deleted_without_deleting_content(context):
    ctx = context
    with pytest.raises(IntegrityError), ctx.database.begin_nested():
        ctx.database.execute(
            text("DELETE FROM sasu.quizzes WHERE content_id=:id"), {"id": ctx.content_id}
        )


@pytest.mark.parametrize("index", [0, 1, 2])
def test_delete_published_draft_and_missing_video(context, index):
    ctx = context
    ctx.content_id = ctx.records["questions"][index]["content_id"]
    assert remove(ctx).status_code == 200


def test_stale_delete_is_rejected_without_changing_content(context):
    ctx = context
    stale = version(ctx)
    updated = ctx.client.patch(
        f"/api/contents/{ctx.content_id}",
        headers=ctx.headers,
        json={**stale, "title": "다른 창에서 저장한 제목"},
    )
    assert updated.status_code == 200, updated.text
    response = ctx.client.request(
        "DELETE",
        f"/api/contents/{ctx.content_id}",
        headers=ctx.headers,
        json={**stale, "confirm": True},
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "EDIT_CONFLICT"
    assert editor(ctx)["detail"]["content"]["title"] == "다른 창에서 저장한 제목"


def test_only_admin_can_delete_content(context):
    ctx = context
    response = ctx.client.request(
        "DELETE",
        f"/api/contents/{ctx.content_id}",
        headers=ctx.learner,
        json={**version(ctx), "confirm": True},
    )
    assert response.status_code == 403


def test_unknown_content_and_query_parameters_are_rejected(context):
    ctx = context
    body = {**version(ctx), "confirm": True}
    response = ctx.client.request("DELETE", "/api/contents/999999", headers=ctx.headers, json=body)
    assert response.status_code == 404
    response = ctx.client.request(
        "DELETE",
        f"/api/contents/{ctx.content_id}?extra=1",
        headers=ctx.headers,
        json=body,
    )
    assert response.status_code == 422


def test_existing_publish_contract_and_statuses_are_unchanged(context):
    ctx = context
    schema = ctx.client.get("/openapi.json").json()
    assert "/api/contents/{content_id}/unpublish" not in schema["paths"]
    assert (
        "PRIVATE"
        not in schema["components"]["schemas"]["ContentSummary"]["properties"]["status"]["enum"]
    )
    assert (
        ctx.client.post(f"/api/contents/{ctx.content_id}/publish", headers=ctx.headers).status_code
        == 200
    )


def test_delete_removes_all_learners_and_old_generations_but_preserves_other_content(context):
    from types import SimpleNamespace

    ctx = context
    seed_history(ctx)
    seed_history(ctx, index=2)
    other = scalar(
        ctx,
        "SELECT user_id FROM sasu.app_users WHERE role='LEARNER' AND user_id<>:id LIMIT 1",
        id=ctx.records["learner"],
    )
    assert other is not None
    alternate = SimpleNamespace(database=ctx.database, records={**ctx.records, "learner": other})
    seed_history(alternate)
    ctx.database.execute(
        text("UPDATE sasu.user_settings SET learning_epoch=2 WHERE user_id=:id"),
        {"id": ctx.records["learner"]},
    )
    q = ctx.records["questions"][0]
    ctx.database.execute(
        text("""INSERT INTO sasu.quiz_attempts
        (attempt_id,user_id,learning_epoch,quiz_id,quiz_version_id,context)
        VALUES (:attempt,:user,2,:quiz,:version,'VIDEO_END')"""),
        {
            "attempt": uuid4(),
            "user": ctx.records["learner"],
            "quiz": q["question_id"],
            "version": q["question_version_id"],
        },
    )
    ctx.database.commit()
    assert remove(ctx).status_code == 200
    for table in [
        "watch_visits",
        "watch_records",
        "content_likes",
        "saved_contents",
        "quiz_attempts",
        "quiz_responses",
        "wrong_answers",
        "learning_events",
        "event_retry_keys",
    ]:
        assert scalar(ctx, f"SELECT count(*) FROM sasu.{table}") == 1, table
    assert scalar(ctx, "SELECT count(*) FROM sasu.quizzes") == 2
