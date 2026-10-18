"""별도 PostgreSQL 테스트 DB에서 기존 마이그레이션·함수·HTTP 계약을 함께 검증한다."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.modules.admin import repository


def scalar(session, sql, **params):
    return session.scalar(text(sql), params)


@pytest.fixture
def records(database):
    session = database
    admin, learner, other, no_state = [
        scalar(
            session,
            """INSERT INTO sasu.app_users (username, display_name, role)
               VALUES (:name, :name, :role) RETURNING user_id""",
            name=name,
            role=role,
        )
        for name, role in (
            ("admin", "ADMIN"),
            ("user1", "LEARNER"),
            ("other", "LEARNER"),
            ("no_state", "LEARNER"),
        )
    ]
    category = scalar(
        session, "INSERT INTO sasu.categories (name) VALUES ('엑셀') RETURNING category_id"
    )
    asset = uuid4()
    session.execute(
        text(
            """INSERT INTO sasu.video_assets
               (video_asset_id, storage_path, original_name,
                mime_type, size_bytes, duration_seconds)
               VALUES (:id, 'test.mp4', 'test.mp4', 'video/mp4', 100, 10)"""
        ),
        {"id": asset},
    )
    content = scalar(
        session,
        """INSERT INTO sasu.contents (created_by_user_id, title, video_asset_id)
           VALUES (:admin, '임시저장 영상', :asset) RETURNING content_id""",
        admin=admin,
        asset=asset,
    )
    empty_content = scalar(
        session,
        "INSERT INTO sasu.contents (created_by_user_id) VALUES (:admin) RETURNING content_id",
        admin=admin,
    )
    for user in (learner, other):
        session.execute(
            text(
                """INSERT INTO sasu.user_settings
                   (user_id, onboarding_status, review_interval, last_content_id)
                   VALUES (:user, 'DONE', 7, :content)"""
            ),
            {"user": user, "content": content},
        )
        session.execute(
            text(
                """INSERT INTO sasu.watch_records
                   (user_id, learning_epoch, content_id, first_played_at, last_watched_at,
                    view_counted_at, completed_at)
                   VALUES (:user, 1, :content, now(), now(), now(),
                           CASE WHEN :completed THEN now() ELSE NULL END)"""
            ),
            {"user": user, "content": content, "completed": user == learner},
        )
        session.execute(
            text(
                """INSERT INTO sasu.content_likes (user_id, learning_epoch, content_id)
                   VALUES (:user, 1, :content)"""
            ),
            {"user": user, "content": content},
        )
    session.execute(
        text("INSERT INTO sasu.user_interests VALUES (:user, :category)"),
        {"user": learner, "category": category},
    )
    session.execute(
        text(
            """INSERT INTO sasu.saved_contents (user_id, learning_epoch, content_id)
               VALUES (:user, 1, :content)"""
        ),
        {"user": learner, "content": content},
    )
    session.execute(
        text(
            """INSERT INTO sasu.watch_visits
               (visit_id, user_id, learning_epoch, content_id, video_asset_id, context)
               VALUES (:id, :user, 1, :content, :asset, 'FEED')"""
        ),
        {"id": uuid4(), "user": learner, "content": content, "asset": asset},
    )
    quiz = scalar(
        session,
        "INSERT INTO sasu.quizzes (content_id) VALUES (:content) RETURNING quiz_id",
        content=content,
    )
    version = scalar(
        session,
        """INSERT INTO sasu.quiz_versions (quiz_id, version_no, question_text, explanation)
           VALUES (:quiz, 1, '질문', '해설') RETURNING quiz_version_id""",
        quiz=quiz,
    )
    options = [
        scalar(
            session,
            """INSERT INTO sasu.quiz_options
               (quiz_version_id, position, option_text, is_correct)
               VALUES (:version, :position, :label, :correct) RETURNING option_id""",
            version=version,
            position=position,
            label=f"보기 {position}",
            correct=position == 1,
        )
        for position in (1, 2, 3)
    ]
    session.execute(
        text("UPDATE sasu.quizzes SET current_version_id = :version WHERE quiz_id = :quiz"),
        {"version": version, "quiz": quiz},
    )
    attempt = uuid4()
    session.execute(
        text(
            """INSERT INTO sasu.quiz_attempts
               (attempt_id, user_id, learning_epoch, quiz_id, quiz_version_id, context)
               VALUES (:id, :user, 1, :quiz, :version, 'VIDEO_END')"""
        ),
        {"id": attempt, "user": learner, "quiz": quiz, "version": version},
    )
    session.execute(
        text(
            """INSERT INTO sasu.quiz_responses
               (attempt_id, quiz_version_id, selected_option_id, result)
               VALUES (:id, :version, :option, 'WRONG')"""
        ),
        {"id": attempt, "version": version, "option": options[1]},
    )
    session.execute(
        text(
            """INSERT INTO sasu.learning_events
               (event_id, user_id, learning_epoch, event_type,
                content_id, quiz_version_id, attempt_id)
               VALUES (:id, :user, 1, 'QUIZ_DISPLAYED', :content, :version, :attempt)"""
        ),
        {
            "id": uuid4(),
            "user": learner,
            "content": content,
            "version": version,
            "attempt": attempt,
        },
    )
    # DB의 지연 검증까지 통과한 자료로 테스트한다.
    session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    session.commit()
    return {
        "admin": admin,
        "learner": learner,
        "other": other,
        "no_state": no_state,
        "content": content,
        "empty_content": empty_content,
        "version": version,
    }


def headers(records, role="admin"):
    return {"X-Actor-Id": str(records[role])}


def reset_url(records):
    return f"/api/users/{records['learner']}/test-records/reset"


def reaction_url(records, empty=False):
    content = records["empty_content" if empty else "content"]
    return f"/api/contents/{content}/statistics/reactions"


def test_statistics_include_drafts_and_real_view_counts(client, records):
    response = client.get(reaction_url(records), headers=headers(records))
    assert response.status_code == 200
    assert response.json() == {
        "view_count": 2,
        "like_count": 2,
        "saved_count": 1,
        "watch_completion": {"numerator": 1, "denominator": 2, "percent": 50.0},
    }


def test_empty_statistics_keep_null_denominator(client, records):
    response = client.get(reaction_url(records, empty=True), headers=headers(records))
    assert response.json() == {
        "view_count": 0,
        "like_count": 0,
        "saved_count": 0,
        "watch_completion": {"numerator": 0, "denominator": 0, "percent": None},
    }


@pytest.mark.parametrize(
    ("actor", "status", "code"),
    [
        (None, 422, "VALIDATION_ERROR"),
        ("learner", 403, "ROLE_NOT_ALLOWED"),
        ("missing", 404, "USER_NOT_FOUND"),
    ],
)
def test_admin_access(client, records, actor, status, code):
    actor_headers = {} if actor is None else {"X-Actor-Id": str(records.get(actor, 9999999))}
    response = client.get(reaction_url(records), headers=actor_headers)
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code


def test_reset_deletes_only_target_learning_and_preserves_materials(client, records, database):
    response = client.post(
        reset_url(records),
        headers=headers(records),
        json={"confirm": True, "expected_record_generation": 0},
    )
    assert response.status_code == 200, response.text
    assert response.json()["record_generation"] == 1
    assert response.json()["clear_client_feed_state"] is True
    assert response.json()["deleted_counts"] == {
        "watch_visits": 1,
        "watch_records": 1,
        "likes": 1,
        "saved_contents": 1,
        "responses": 1,
        "attempts": 1,
        "wrong_answers": 1,
        "events": 1,
    }
    state = (
        database.execute(
            text("SELECT * FROM sasu.user_settings WHERE user_id = :user"),
            {"user": records["learner"]},
        )
        .mappings()
        .one()
    )
    assert (state["learning_epoch"], state["last_content_id"]) == (2, None)
    assert (state["onboarding_status"], state["review_interval"]) == ("DONE", 7)
    assert scalar(database, "SELECT count(*) FROM sasu.user_interests") == 1
    assert scalar(database, "SELECT count(*) FROM sasu.contents") == 2
    assert scalar(database, "SELECT count(*) FROM sasu.video_assets") == 1
    assert scalar(database, "SELECT count(*) FROM sasu.quiz_versions") == 1
    remaining = client.get(reaction_url(records), headers=headers(records)).json()
    assert (remaining["view_count"], remaining["like_count"], remaining["saved_count"]) == (1, 1, 0)


def test_reset_retry_cannot_remove_new_learning(client, records, database):
    payload = {"confirm": True, "expected_record_generation": 0}
    assert (
        client.post(reset_url(records), headers=headers(records), json=payload).status_code == 200
    )
    database.execute(
        text(
            """INSERT INTO sasu.content_likes (user_id, learning_epoch, content_id)
               VALUES (:user, 2, :content)"""
        ),
        {"user": records["learner"], "content": records["content"]},
    )
    database.commit()
    response = client.post(reset_url(records), headers=headers(records), json=payload)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "RECORD_GENERATION_MISMATCH"
    assert scalar(database, "SELECT count(*) FROM sasu.content_likes") == 2


@pytest.mark.parametrize("target", ["admin", "no_state", "missing"])
def test_reset_requires_learner_state(client, records, target):
    target_id = records.get(target, 9999999)
    response = client.post(
        f"/api/users/{target_id}/test-records/reset",
        headers=headers(records),
        json={"confirm": True, "expected_record_generation": 0},
    )
    assert response.status_code == 404


def test_confirmation_false_has_business_error(client, records):
    response = client.post(
        reset_url(records),
        headers=headers(records),
        json={"confirm": False, "expected_record_generation": 0},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "RESET_CONFIRMATION_REQUIRED"


@pytest.mark.parametrize(
    "payload",
    [
        {"confirm": "true", "expected_record_generation": 0},
        {"confirm": True, "expected_record_generation": True},
        {"confirm": True, "expected_record_generation": -1},
        {"confirm": True, "expected_record_generation": 0, "unknown": "value"},
    ],
)
def test_reset_rejects_invalid_payload(client, records, payload):
    response = client.post(reset_url(records), headers=headers(records), json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_unknown_query_and_missing_content(client, records):
    response = client.get(reaction_url(records) + "?unknown=1", headers=headers(records))
    assert response.status_code == 422
    response = client.get("/api/contents/9999999/statistics/reactions", headers=headers(records))
    assert response.status_code == 404


def test_malformed_json(client, records):
    response = client.post(
        reset_url(records),
        headers={**headers(records), "Content-Type": "application/json"},
        content="{",
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_REQUEST"


def test_failed_reset_rolls_back_and_hides_database_details(client, records, database, monkeypatch):
    original_reset = repository.reset_learning

    def fail_after_delete(session, user_id, expected_epoch):
        original_reset(session, user_id, expected_epoch)
        raise OperationalError("secret SQL", {}, Exception("secret DB password"))

    monkeypatch.setattr(repository, "reset_learning", fail_after_delete)
    response = client.post(
        reset_url(records),
        headers=headers(records),
        json={"confirm": True, "expected_record_generation": 0},
    )
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in response.text
    assert scalar(database, "SELECT count(*) FROM sasu.content_likes") == 2
    assert scalar(database, "SELECT count(*) FROM sasu.quiz_responses") == 1
    assert (
        scalar(
            database,
            "SELECT learning_epoch FROM sasu.user_settings WHERE user_id = :user",
            user=records["learner"],
        )
        == 1
    )


def test_old_epoch_write_is_rejected_after_reset(client, records, database):
    assert (
        client.post(
            reset_url(records),
            headers=headers(records),
            json={"confirm": True, "expected_record_generation": 0},
        ).status_code
        == 200
    )
    with pytest.raises(IntegrityError), database.begin_nested():
        database.execute(
            text(
                """INSERT INTO sasu.saved_contents (user_id, learning_epoch, content_id)
                   VALUES (:user, 1, :content)"""
            ),
            {"user": records["learner"], "content": records["content"]},
        )
