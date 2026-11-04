"""실제 PostgreSQL에서 비공개 이력 보존·집계 제외·전체 삭제의 원자성을 검증한다."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import get_settings
from app.integrations.storage import LocalVideoStorage
from app.modules.contents import deletion_repository
from app.modules.contents.asset_cleanup import cleanup_assets
from app.modules.dashboard import repository as dashboard_repository
from app.modules.feeds.repository import watch_context


@pytest.fixture
def catalog(database, client):
    users = {}
    for name, role in (("admin", "ADMIN"), ("learner", "LEARNER"), ("other", "LEARNER")):
        users[name] = database.scalar(
            text("""
            INSERT INTO sasu.app_users (username, display_name, role)
            VALUES (:name, :name, :role) RETURNING user_id
        """),
            {"name": name, "role": role},
        )
        if role == "LEARNER":
            database.execute(
                text("INSERT INTO sasu.user_settings (user_id) VALUES (:id)"), {"id": users[name]}
            )
    category = database.scalar(
        text("INSERT INTO sasu.categories (name) VALUES ('분야') RETURNING category_id")
    )
    tag = database.scalar(text("INSERT INTO sasu.tags (name) VALUES ('태그') RETURNING tag_id"))
    database.commit()

    def call(method, path, *, who="admin", expected=200, **kwargs):
        extra_headers = kwargs.pop("headers", {})
        result = client.request(
            method,
            "/api" + path,
            headers={"X-Actor-Id": str(users[who]), **extra_headers},
            **kwargs,
        )
        database.commit()
        assert result.status_code == expected, result.text
        return result.json() if result.content else None

    def content(title="공개 콘텐츠", status="PUBLISHED"):
        asset = uuid4()
        root = get_settings().video_storage_root
        root.mkdir(parents=True, exist_ok=True)
        path = f"{asset}.mp4"
        (root / path).write_bytes(b"fixture")
        database.execute(
            text("""
            INSERT INTO sasu.video_assets
            (video_asset_id, storage_path, original_name, mime_type, size_bytes, duration_seconds)
            VALUES (:id, :path, :path, 'video/mp4', 7, 10)
        """),
            {"id": asset, "path": path},
        )
        cid = database.scalar(
            text("""
            INSERT INTO sasu.contents
            (created_by_user_id, video_asset_id, category_id, title, core_content,
             source, reviewed_on, status, published_at)
            VALUES (:admin, :asset, :category, :title, '핵심 내용', '출처', current_date,
                    :status, CASE WHEN CAST(:status AS varchar)='PUBLISHED' THEN now() END)
            RETURNING content_id
        """),
            {
                "admin": users["admin"],
                "asset": asset,
                "category": category,
                "title": title,
                "status": status,
            },
        )
        database.execute(
            text("INSERT INTO sasu.content_tags VALUES (:id, :tag)"), {"id": cid, "tag": tag}
        )
        database.commit()
        return cid, root / path

    return {"users": users, "category": category, "tag": tag, "call": call, "content": content}


def question(catalog, content_id):
    return catalog["call"](
        "POST",
        f"/contents/{content_id}/question",
        expected=201,
        json={
            "question_type": "OX",
            "question_text": "문제",
            "explanation": "해설",
            "options": [
                {"option_order": 1, "option_text": "O", "is_correct": True},
                {"option_order": 2, "option_text": "X", "is_correct": False},
            ],
        },
    )


def learn(database, catalog, cid, version, *, who="learner", result="CORRECT"):
    user = catalog["users"][who]
    parameters = {"user": user, "content": cid}
    database.execute(
        text("""
        INSERT INTO sasu.watch_records
        (user_id, learning_epoch, content_id, first_played_at, last_watched_at,
         completed_at, view_counted_at, max_coverage_ratio)
        VALUES (:user, 1, :content, now(), now(), now(), now(), 1)
        ON CONFLICT (user_id, content_id) DO NOTHING
    """),
        parameters,
    )
    for table in ("content_likes", "saved_contents"):
        database.execute(
            text(f"""
            INSERT INTO sasu.{table} (user_id, learning_epoch, content_id)
            VALUES (:user, 1, :content) ON CONFLICT DO NOTHING
        """),
            parameters,
        )
    attempt = uuid4()
    database.execute(
        text("""
        INSERT INTO sasu.quiz_attempts
        (attempt_id, user_id, learning_epoch, quiz_id, quiz_version_id, context)
        VALUES (:id, :user, 1, :quiz, :version, 'VIDEO_END')
    """),
        {
            "id": attempt,
            "user": user,
            "quiz": version["question_id"],
            "version": version["question_version_id"],
        },
    )
    database.execute(
        text("""
        INSERT INTO sasu.learning_events
        (event_id, user_id, learning_epoch, event_type, content_id, quiz_version_id, attempt_id)
        VALUES (:id, :user, 1, 'QUIZ_DISPLAYED', :content, :version, :attempt)
    """),
        {
            **parameters,
            "id": uuid4(),
            "attempt": attempt,
            "version": version["question_version_id"],
        },
    )
    option = (
        None
        if result == "SKIPPED"
        else next(
            item["option_id"]
            for item in version["options"]
            if item["is_correct"] == (result == "CORRECT")
        )
    )
    response = database.scalar(
        text("""
        INSERT INTO sasu.quiz_responses
        (attempt_id, quiz_version_id, selected_option_id, result)
        VALUES (:attempt, :version, :option, :result) RETURNING response_id
    """),
        {
            "attempt": attempt,
            "version": version["question_version_id"],
            "option": option,
            "result": result,
        },
    )
    database.execute(
        text("""
        UPDATE sasu.user_settings SET last_content_id = :content WHERE user_id = :user
    """),
        parameters,
    )
    database.commit()
    return attempt, response


def scalar(database, statement, **parameters):
    value = database.scalar(text(statement), parameters)
    database.commit()
    return value


def course(catalog, ids):
    call = catalog["call"]
    result = call("POST", "/curriculums", json={"title": "시리즈"}, expected=201)
    cid = result["summary"]["curriculum_id"]
    call("PUT", f"/curriculums/{cid}/steps", json={"content_ids": ids})
    return cid


def test_private_roundtrip_hides_learner_data_and_restores_history(catalog, database):
    call = catalog["call"]
    hidden, path = catalog["content"]()
    visible, _ = catalog["content"]("다른 콘텐츠")
    version = question(catalog, hidden)
    attempt, response = learn(database, catalog, hidden, version)
    learn(database, catalog, hidden, version, result="SKIPPED")
    series = course(catalog, [hidden, visible])
    before = call("GET", f"/contents/{hidden}?view=editor")
    hidden_result = call("POST", f"/contents/{hidden}/unpublish")
    assert hidden_result["detail"]["content"]["status"] == "PRIVATE"
    assert "preview=true" in hidden_result["detail"]["content"]["video_url"]
    assert (
        call("POST", f"/contents/{hidden}/unpublish")["updated_at"] == hidden_result["updated_at"]
    )
    call("GET", f"/contents/{hidden}", who="learner", expected=404)
    call("GET", f"/contents/{hidden}/video", who="learner", expected=404)
    call("GET", f"/responses/{response}", who="learner", expected=404)
    call(
        "GET",
        f"/users/{catalog['users']['learner']}/question-attempts/{attempt}",
        who="learner",
        expected=404,
    )
    assert call("GET", f"/responses/{response}")["response_id"] == response
    assert path.exists()
    learner_id = catalog["users"]["learner"]
    summary = call("GET", f"/users/{learner_id}/dashboard", who="learner")
    for field in ("watched_content_count", "completed_content_count", "answered_count"):
        assert summary[field] == 0
    metrics = dashboard_repository.summary(database, learner_id)
    assert metrics["liked_count"] == metrics["saved_count"] == metrics["skipped_count"] == 0
    database.commit()
    learner_course = call("GET", f"/curriculums/{series}", who="learner")
    assert learner_course["summary"]["total_steps"] == 1
    assert learner_course["summary"]["completed_steps"] == 0
    assert [(s["content_id"], s["step_order"]) for s in learner_course["steps"]] == [(visible, 1)]
    assert call("GET", f"/curriculums/{series}?view=editor")["summary"]["total_steps"] == 2
    assert (
        scalar(
            database,
            "SELECT total_steps FROM sasu.curriculum_progress "
            "WHERE user_id=:user AND curriculum_id=:id",
            user=learner_id,
            id=series,
        )
        == 1
    )
    assert watch_context(database, learner_id, 1) == (frozenset(), frozenset())
    database.commit()
    assert scalar(database, "SELECT count(*) FROM sasu.quiz_responses") == 2
    assert call("GET", f"/contents/{hidden}/statistics")["reactions"]["like_count"] == 1
    assert call("GET", "/contents?status=PRIVATE")["total"] == 1
    assert call("GET", "/contents", who="learner")["total"] == 1
    published = call("POST", f"/contents/{hidden}/publish")
    assert published["detail"]["published_at"] == before["detail"]["published_at"]
    restored = call("GET", f"/users/{learner_id}/dashboard", who="learner")
    assert restored["watched_content_count"] == restored["answered_count"] == 1
    metrics = dashboard_repository.summary(database, learner_id)
    assert metrics["liked_count"] == metrics["saved_count"] == metrics["skipped_count"] == 1
    database.commit()
    restored_course = call("GET", f"/curriculums/{series}", who="learner")
    assert restored_course["summary"]["total_steps"] == 2
    assert restored_course["summary"]["completed_steps"] == 1
    assert call("GET", f"/responses/{response}", who="learner")["response_id"] == response


def test_delete_removes_owned_history_files_and_reorders_series(catalog, database):
    call = catalog["call"]
    target, path = catalog["content"]()
    keep, keep_path = catalog["content"]("유지 콘텐츠")
    version = question(catalog, target)
    learn(database, catalog, target, version, result="WRONG")
    version = call(
        "POST",
        f"/questions/{version['question_id']}/versions",
        expected=201,
        json={
            "expected_current_version_id": version["question_version_id"],
            "question_type": "OX",
            "question_text": "개정 문제",
            "explanation": "개정 해설",
            "options": [
                {"option_order": 1, "option_text": "O", "is_correct": True},
                {"option_order": 2, "option_text": "X", "is_correct": False},
            ],
        },
    )
    learn(database, catalog, target, version)
    learn(database, catalog, target, version, who="other", result="WRONG")
    keep_version = question(catalog, keep)
    learn(database, catalog, keep, keep_version)
    series = course(catalog, [target, keep])
    old_asset = uuid4()
    old_path = get_settings().video_storage_root / f"{old_asset}.mp4"
    old_path.write_bytes(b"old-video")
    database.execute(
        text("""
        INSERT INTO sasu.video_assets
        (video_asset_id, storage_path, original_name, mime_type, size_bytes, duration_seconds)
        VALUES (:id, :path, :path, 'video/mp4', 9, 10)
    """),
        {"id": old_asset, "path": old_path.name},
    )
    database.execute(
        text("""
        INSERT INTO sasu.watch_visits
        (visit_id, user_id, learning_epoch, content_id, video_asset_id, context)
        VALUES (:visit, :user, 1, :content, :asset, 'FEED')
    """),
        {
            "visit": uuid4(),
            "user": catalog["users"]["learner"],
            "content": target,
            "asset": old_asset,
        },
    )
    database.commit()
    thumbnail = b"\x89PNG\r\n\x1a\n" + b"test-image"
    call(
        "PUT",
        f"/contents/{target}/thumbnail",
        expected=204,
        files={"file": ("image.png", thumbnail, "image/png")},
    )
    image_root = get_settings().image_storage_root
    assert any(image_root.iterdir())
    call("DELETE", f"/contents/{target}", json={"confirm": True}, expected=204)
    call("GET", f"/contents/{target}?view=editor", expected=404)
    call("DELETE", f"/contents/{target}", json={"confirm": True}, expected=404)
    assert not path.exists() and not old_path.exists() and keep_path.exists()
    assert not list(image_root.iterdir())
    for table in (
        "contents",
        "quizzes",
        "quiz_versions",
        "watch_records",
        "content_likes",
        "saved_contents",
    ):
        assert scalar(database, f"SELECT count(*) FROM sasu.{table}") == 1
    assert scalar(database, "SELECT count(*) FROM sasu.quiz_options") == 2
    assert scalar(database, "SELECT count(*) FROM sasu.watch_visits") == 0
    assert scalar(database, "SELECT count(*) FROM sasu.video_assets") == 1
    assert scalar(database, "SELECT count(*) FROM sasu.quiz_attempts") == 1
    assert scalar(database, "SELECT count(*) FROM sasu.quiz_responses") == 1
    assert scalar(database, "SELECT count(*) FROM sasu.wrong_answers") == 0
    assert scalar(database, "SELECT count(*) FROM sasu.learning_events") == 1
    assert (
        scalar(
            database,
            "SELECT last_content_id FROM sasu.user_settings WHERE user_id=:id",
            id=catalog["users"]["other"],
        )
        is None
    )
    for table in ("categories", "tags", "curricula"):
        assert scalar(database, f"SELECT count(*) FROM sasu.{table}") == 1
    assert scalar(database, "SELECT count(*) FROM sasu.app_users") == 3
    remaining = call("GET", f"/curriculums/{series}?view=editor")["steps"]
    assert [(s["content_id"], s["step_order"]) for s in remaining] == [(keep, 1)]
    assert scalar(database, "SELECT count(*) FROM sasu.asset_cleanup_jobs") == 0
    database.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    database.commit()


def test_permissions_confirmation_and_draft_transition(catalog):
    call = catalog["call"]
    target, path = catalog["content"](status="DRAFT")
    call("POST", f"/contents/{target}/unpublish", expected=409)
    call("POST", f"/contents/{target}/unpublish", who="learner", expected=403)
    call("DELETE", f"/contents/{target}", who="learner", expected=403, json={"confirm": True})
    for body in ({"confirm": False}, {"confirm": "true"}, {}, {"confirm": True, "extra": 1}):
        call("DELETE", f"/contents/{target}", expected=422, json=body)
        assert path.exists()
    call("DELETE", f"/contents/{target}", expected=204, json={"confirm": True})


def test_failed_delete_rolls_back_and_keeps_files(catalog, database, monkeypatch):
    target, path = catalog["content"]()
    version = question(catalog, target)
    learn(database, catalog, target, version)

    def fail(*args):
        raise SQLAlchemyError("injected database failure")

    monkeypatch.setattr(deletion_repository, "delete_assets", fail)
    catalog["call"]("DELETE", f"/contents/{target}", json={"confirm": True}, expected=500)
    assert path.exists()
    for table in ("contents", "quizzes", "quiz_versions", "quiz_responses", "content_likes"):
        assert scalar(database, f"SELECT count(*) FROM sasu.{table}") == 1


def test_failed_file_cleanup_is_durable_and_retryable(catalog, database, monkeypatch):
    target, path = catalog["content"]()

    def fail(*args):
        raise PermissionError("injected file error")

    with monkeypatch.context() as patch:
        patch.setattr(LocalVideoStorage, "delete", fail)
        catalog["call"]("DELETE", f"/contents/{target}", json={"confirm": True}, expected=204)
    assert path.exists()
    assert scalar(database, "SELECT count(*) FROM sasu.asset_cleanup_jobs") == 1
    assert cleanup_assets(database) == 1
    assert not path.exists()
    assert scalar(database, "SELECT count(*) FROM sasu.asset_cleanup_jobs") == 0


def test_quiz_history_still_rejects_individual_deletion(catalog, database):
    target, _ = catalog["content"]()
    question(catalog, target)
    for table in ("quiz_options", "quiz_versions", "quizzes"):
        with pytest.raises(IntegrityError), database.begin_nested():
            database.execute(text(f"DELETE FROM sasu.{table}"))
    database.commit()
    assert scalar(database, "SELECT count(*) FROM sasu.quiz_options") == 2


def test_private_blocks_stale_actions_and_media_but_admin_can_preview(catalog, database):
    call = catalog["call"]
    target, _ = catalog["content"]()
    version = question(catalog, target)
    learn(database, catalog, target, version, result="WRONG")
    thumbnail = b"\x89PNG\r\n\x1a\n" + b"private-image"
    call(
        "PUT",
        f"/contents/{target}/thumbnail",
        expected=204,
        files={"file": ("image.png", thumbnail, "image/png")},
    )
    hidden = call("POST", f"/contents/{target}/unpublish")
    preview = hidden["detail"]["content"]
    assert "preview=true" in preview["thumbnail_url"]
    user = catalog["users"]["learner"]
    call("GET", f"/contents/{target}/thumbnail", who="learner", expected=404)
    call(
        "GET",
        f"/contents/{target}/thumbnail?preview=true&actor_id={user}",
        who="learner",
        expected=403,
    )
    # 관리자 미리보기는 권한 확인과 실제 파일 검사를 모두 거친다.
    from app.modules.contents import thumbnail_service, video_service
    from app.modules.contents.schemas import VideoQuery

    assert (
        thumbnail_service.get_content_thumbnail(
            database, target, preview=True, actor_id=catalog["users"]["admin"]
        )[0]
        == thumbnail
    )
    video = video_service.get_video(
        database,
        target,
        VideoQuery(preview=True, actor_id=catalog["users"]["admin"]),
        LocalVideoStorage(get_settings().video_storage_root),
        None,
    )
    assert b"".join(video.chunks()) == b"fixture"
    database.commit()
    assert call("GET", f"/users/{user}/saved-contents", who="learner")["total"] == 0
    for resource in ("like", "saved"):
        call(
            "DELETE",
            f"/users/{user}/contents/{target}/{resource}",
            who="learner",
            expected=404,
            headers={"X-Record-Generation": "0"},
        )
    assert scalar(database, "SELECT count(*) FROM sasu.content_likes") == 1
    assert scalar(database, "SELECT count(*) FROM sasu.saved_contents") == 1


def test_private_reset_does_not_resurrect_erased_learning(catalog, database):
    call = catalog["call"]
    target, _ = catalog["content"]()
    version = question(catalog, target)
    learn(database, catalog, target, version)
    call("POST", f"/contents/{target}/unpublish")
    user = catalog["users"]["learner"]
    call(
        "POST",
        f"/users/{user}/test-records/reset",
        json={"confirm": True, "expected_record_generation": 0},
    )
    call("POST", f"/contents/{target}/publish")
    assert scalar(database, "SELECT count(*) FROM sasu.quiz_responses") == 0
    assert scalar(database, "SELECT count(*) FROM sasu.saved_contents") == 0
    assert call("GET", f"/users/{user}/dashboard", who="learner")["completed_content_count"] == 0


def test_delete_preserves_thumbnail_still_used_by_a_series(catalog, database):
    call = catalog["call"]
    target, path = catalog["content"]()
    series = course(catalog, [target])
    call(
        "PUT",
        f"/contents/{target}/thumbnail",
        expected=204,
        files={"file": ("image.png", b"\x89PNG\r\n\x1a\nshared", "image/png")},
    )
    database.execute(
        text("""
        UPDATE sasu.curricula SET thumbnail_image_id = (
            SELECT thumbnail_image_id FROM sasu.contents WHERE content_id=:content
        ) WHERE curriculum_id=:series
    """),
        {"content": target, "series": series},
    )
    database.commit()
    call("DELETE", f"/contents/{target}", expected=204, json={"confirm": True})
    assert not path.exists()
    assert scalar(database, "SELECT count(*) FROM sasu.image_assets") == 1
    assert len(list(get_settings().image_storage_root.iterdir())) == 1
    detail = call("GET", f"/curriculums/{series}?view=editor")
    assert detail["summary"]["total_steps"] == 0
    assert detail["summary"]["thumbnail_url"]
