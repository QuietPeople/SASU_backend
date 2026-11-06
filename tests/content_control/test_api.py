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
from app.modules.contents import lifecycle_repository


def editor(ctx, content_id=None):
    response = ctx.client.get(
        f"/api/contents/{content_id or ctx.content_id}?view=editor", headers=ctx.headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def version(ctx, content_id=None):
    return {"expected_updated_at": editor(ctx, content_id)["updated_at"]}


def hide(ctx):
    response = ctx.client.post(
        f"/api/contents/{ctx.content_id}/unpublish", headers=ctx.headers, json=version(ctx)
    )
    assert response.status_code == 200, response.text
    return response.json()


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


def test_private_is_distinct_hidden_and_republish_restores_history(context):
    ctx = context
    seed_history(ctx)
    thumb = image(ctx)
    before = editor(ctx)
    uid = ctx.records["learner"]
    hidden = hide(ctx)
    assert hidden["detail"]["content"]["status"] == "PRIVATE"
    assert hidden["detail"]["published_at"] == before["detail"]["published_at"]
    assert "preview=true" in hidden["detail"]["content"]["video_url"]
    assert ctx.client.get(hidden["detail"]["content"]["video_url"]).status_code == 200
    assert ctx.client.get(hidden["detail"]["content"]["thumbnail_url"]).status_code == 200
    for path in (
        f"/api/contents/{ctx.content_id}",
        f"/api/contents/{ctx.content_id}/video",
        f"/api/contents/{ctx.content_id}/thumbnail",
        f"/api/contents/{ctx.content_id}/question",
    ):
        assert ctx.client.get(path, headers=ctx.learner).status_code == 404
    assert ctx.client.get(thumb.split("?")[0]).status_code == 404
    listed = ctx.client.get("/api/contents?status=PRIVATE", headers=ctx.headers).json()
    assert [c["content_id"] for c in listed["items"]] == [ctx.content_id]
    assert ctx.client.get("/api/contents?status=PRIVATE", headers=ctx.learner).status_code == 403
    dashboard = ctx.client.get(f"/api/users/{uid}/dashboard", headers=ctx.learner).json()
    assert dashboard["watched_content_count"] == dashboard["answered_count"] == 0
    assert dashboard["pending_question_count"] == 0
    for table in (
        "watch_records",
        "content_likes",
        "saved_contents",
        "quiz_attempts",
        "quiz_responses",
        "wrong_answers",
        "learning_events",
        "event_retry_keys",
    ):
        assert scalar(ctx, f"SELECT count(*) FROM sasu.{table}") == 1
    assert (
        scalar(ctx, "SELECT last_content_id FROM sasu.user_settings WHERE user_id=:uid", uid=uid)
        == ctx.content_id
    )
    restored = ctx.client.post(
        f"/api/contents/{ctx.content_id}/publish", headers=ctx.headers, json=version(ctx)
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["detail"]["published_at"] == before["detail"]["published_at"]
    detail = ctx.client.get(f"/api/contents/{ctx.content_id}", headers=ctx.learner).json()
    assert detail["content"]["liked"] and detail["content"]["saved"]
    assert detail["content"]["watch_completed"]
    dashboard = ctx.client.get(f"/api/users/{uid}/dashboard", headers=ctx.learner).json()
    assert dashboard["watched_content_count"] == dashboard["answered_count"] == 1
    assert dashboard["pending_question_count"] == 1


def test_private_excluded_from_series_denominator_and_restored(context):
    ctx = context
    seed_history(ctx, correct=True)
    cur = series(ctx)
    uid = ctx.records["learner"]
    before = ctx.client.get(f"/api/curriculums/{cur}", headers=ctx.learner).json()
    assert before["summary"]["total_steps"] == 3
    assert before["summary"]["completed_steps"] == 1
    hide(ctx)
    progress = ctx.client.get(
        f"/api/users/{uid}/curriculums/{cur}/progress", headers=ctx.learner
    ).json()
    assert progress["total_steps"] == 2 and progress["completed_steps"] == 0
    assert [s["step_order"] for s in progress["steps"]] == [1, 2]
    assert all(s["content_id"] != ctx.content_id for s in progress["steps"])
    view = scalar(
        ctx,
        """SELECT total_steps FROM sasu.curriculum_progress
        WHERE user_id=:uid AND curriculum_id=:cur""",
        uid=uid,
        cur=cur,
    )
    assert view == 2
    admin = ctx.client.get(f"/api/curriculums/{cur}?view=editor", headers=ctx.headers).json()
    assert admin["summary"]["total_steps"] == 3
    restored = ctx.client.post(
        f"/api/contents/{ctx.content_id}/publish", headers=ctx.headers, json=version(ctx)
    )
    assert restored.status_code == 200
    after = ctx.client.get(f"/api/curriculums/{cur}", headers=ctx.learner).json()
    assert after["summary"] == before["summary"]


@pytest.mark.parametrize("action", ["unpublish", "publish", "delete"])
def test_stale_actions_are_rejected(context, action):
    ctx = context
    stale = version(ctx)
    hide(ctx)
    if action == "delete":
        response = ctx.client.request(
            "DELETE",
            f"/api/contents/{ctx.content_id}",
            headers=ctx.headers,
            json={**stale, "confirm": True},
        )
    else:
        response = ctx.client.post(
            f"/api/contents/{ctx.content_id}/{action}", headers=ctx.headers, json=stale
        )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "EDIT_CONFLICT"
    assert editor(ctx)["detail"]["content"]["status"] == "PRIVATE"


@pytest.mark.parametrize("confirmation", [False, None, 1, "true"])
def test_delete_requires_explicit_boolean_confirmation(context, confirmation):
    assert remove(context, confirm=confirmation).status_code == 422
    assert editor(context)["detail"]["content"]["status"] == "PUBLISHED"


@pytest.mark.parametrize("action", ["delete", "unpublish"])
def test_only_admin_can_control_content(context, action):
    ctx = context
    method = "DELETE" if action == "delete" else "POST"
    path = f"/api/contents/{ctx.content_id}" + ("" if action == "delete" else "/unpublish")
    response = ctx.client.request(
        method,
        path,
        headers=ctx.learner,
        json={**version(ctx), **({"confirm": True} if action == "delete" else {})},
    )
    assert response.status_code == 403


def test_draft_cannot_be_mislabeled_private(context):
    ctx = context
    cid = ctx.records["questions"][1]["content_id"]
    response = ctx.client.post(
        f"/api/contents/{cid}/unpublish", headers=ctx.headers, json=version(ctx, cid)
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CONTENT_NOT_PUBLISHED"


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
    original = lifecycle_repository.delete_owned_rows
    paths = list(get_settings().video_storage_root.iterdir())

    def fail(session, content):
        original(session, content)
        raise OperationalError("forced failure", {}, Exception())

    monkeypatch.setattr(lifecycle_repository, "delete_owned_rows", fail)
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


def test_unknown_deleted_content_and_query_parameters_are_rejected(context):
    ctx = context
    stamp = version(ctx)
    for method, path, body in [
        ("POST", "/api/contents/999999/unpublish", stamp),
        ("DELETE", "/api/contents/999999", {**stamp, "confirm": True}),
        ("POST", f"/api/contents/{ctx.content_id}/unpublish?extra=1", stamp),
    ]:
        response = ctx.client.request(method, path, headers=ctx.headers, json=body)
        assert response.status_code in (404, 422)


def test_quiz_parent_cannot_be_deleted_without_deleting_content(context):
    ctx = context
    with pytest.raises(IntegrityError), ctx.database.begin_nested():
        ctx.database.execute(
            text("DELETE FROM sasu.quizzes WHERE content_id=:id"), {"id": ctx.content_id}
        )


def test_private_attempt_and_response_are_hidden_until_republished(context):
    ctx = context
    ids = seed_history(ctx)
    response_id = scalar(
        ctx, "SELECT response_id FROM sasu.quiz_responses WHERE attempt_id=:id", id=ids["attempt"]
    )
    hide(ctx)
    uid = ctx.records["learner"]
    attempt = f"/api/users/{uid}/question-attempts/{ids['attempt']}"
    assert ctx.client.get(attempt, headers=ctx.learner).status_code == 404
    assert ctx.client.get(f"/api/responses/{response_id}", headers=ctx.learner).status_code == 404
    assert ctx.client.get(f"/api/responses/{response_id}", headers=ctx.headers).status_code == 200
    assert (
        ctx.client.post(
            f"/api/contents/{ctx.content_id}/publish", headers=ctx.headers, json=version(ctx)
        ).status_code
        == 200
    )
    assert ctx.client.get(attempt, headers=ctx.learner).status_code == 200
    assert ctx.client.get(f"/api/responses/{response_id}", headers=ctx.learner).status_code == 200


@pytest.mark.parametrize("index", [0, 1, 2])
def test_delete_private_draft_and_missing_video(context, index):
    ctx = context
    ctx.content_id = ctx.records["questions"][index]["content_id"]
    if index == 0:
        hide(ctx)
    assert remove(ctx).status_code == 200
