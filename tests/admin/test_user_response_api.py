"""실제 PostgreSQL에서 공개 사용자 조회·응답 소유권·과거 결과 보존 검증."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.modules.responses import repository as responses_repository
from app.modules.users import repository as users_repository
from app.modules.users import service as users_service
from app.modules.users.models import User as UserModel
from app.modules.users.models import UserRole

SUBMITTED_AT = datetime(2026, 10, 15, 3, 6, tzinfo=timezone.utc)


@pytest.fixture
def users(database):
    records = {}
    # 삽입 순서와 ID 순서를 달리하고 int32보다 큰 사용자 ID도 검증한다.
    for offset, username, name, role in (
        (3, "admin", "관리자", "ADMIN"),
        (1, "learner", "학습자", "LEARNER"),
        (2, "other", "다른 학습자", "LEARNER"),
    ):
        user_id = 2**31 + offset
        database.execute(
            text("""INSERT INTO sasu.app_users (user_id, username, display_name, role)
                    OVERRIDING SYSTEM VALUE VALUES (:id, :username, :name, :role)"""),
            {"id": user_id, "username": username, "name": name, "role": role},
        )
        records[username] = {"user_id": user_id, "name": name, "role": role}
    database.commit()
    return records


def headers(users, username="learner"):
    return {"X-Actor-Id": str(users[username]["user_id"])}


@pytest.fixture
def question(client, database, users):
    for username in ("learner", "other"):
        database.execute(
            text("INSERT INTO sasu.user_settings (user_id) VALUES (:id)"),
            {"id": users[username]["user_id"]},
        )
    content_id = database.scalar(
        text("""INSERT INTO sasu.contents (created_by_user_id, title)
                VALUES (:admin, '과거 결과 조회용 초안') RETURNING content_id"""),
        {"admin": users["admin"]["user_id"]},
    )
    database.commit()
    response = client.post(
        f"/api/contents/{content_id}/question",
        headers=headers(users, "admin"),
        json=question_body(),
    )
    assert response.status_code == 201, response.text
    database.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    database.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    database.commit()
    return response.json()


def question_body(kind="MCQ_3"):
    labels = ["O", "X"] if kind == "OX" else [f"보기{i}" for i in range(1, 5)]
    if kind == "MCQ_3":
        labels.pop()
    return {
        "question_type": kind,
        "question_text": "제출 당시 문제",
        "explanation": "제출 당시 해설",
        # 요청 순서와 무관하게 option_order로 정렬되어야 한다.
        "options": [
            {"option_order": index, "option_text": label, "is_correct": index == 2}
            for index, label in reversed(list(enumerate(labels, start=1)))
        ],
    }


def add_response(
    database, users, question, result="WRONG", context="VIDEO_END", username="learner"
):
    attempt_id = uuid4()
    database.execute(
        text("""INSERT INTO sasu.quiz_attempts
                (attempt_id, user_id, learning_epoch, quiz_id, quiz_version_id, context)
                VALUES (:id, :user, 1, :question, :version, :context)"""),
        {
            "id": attempt_id,
            "user": users[username]["user_id"],
            "question": question["question_id"],
            "version": question["question_version_id"],
            "context": context,
        },
    )
    selected = None
    if result != "SKIPPED":
        selected = next(
            option["option_id"]
            for option in question["options"]
            if option["is_correct"] == (result == "CORRECT")
        )
    record = (
        database.execute(
            text("""INSERT INTO sasu.quiz_responses
                    (attempt_id, quiz_version_id, selected_option_id, result, submitted_at)
                    VALUES (:id, :version, :option, :result, :time)
                    RETURNING response_id, attempt_id, selected_option_id"""),
            {
                "id": attempt_id,
                "version": question["question_version_id"],
                "option": selected,
                "result": result,
                "time": SUBMITTED_AT,
            },
        )
        .mappings()
        .one()
    )
    database.commit()
    return dict(record)


def snapshot(database):
    return {
        table: database.scalar(text(f"SELECT jsonb_agg(to_jsonb(t)) FROM sasu.{table} t"))
        for table in (
            "app_users",
            "user_settings",
            "quiz_attempts",
            "quiz_responses",
            "wrong_answers",
            "learning_events",
        )
    }


def test_users_empty_list_does_not_create_mock_users(client, database):
    assert client.get("/api/users").json() == {"items": []}
    assert database.scalar(text("SELECT count(*) FROM sasu.app_users")) == 0
    assert database.scalar(text("SELECT count(*) FROM sasu.user_settings")) == 0


def test_public_user_list_and_detail_only_return_identification(client, database, users):
    before = snapshot(database)
    response = client.get("/api/users")
    assert response.status_code == 200
    assert response.json() == {"items": sorted(users.values(), key=lambda user: user["user_id"])}
    for user in users.values():
        detail = client.get(f"/api/users/{user['user_id']}")
        assert detail.status_code == 200 and detail.json() == user
    # 공통 조회에는 행위자·세대 헤더가 필요하지 않고 설정도 자동 생성하지 않는다.
    assert client.get("/api/users", headers={"X-Actor-Id": "unknown"}).status_code == 200
    assert snapshot(database) == before


def test_upload_user_helpers_return_orm_and_leave_transaction_to_caller(database, users):
    with database.begin():
        user = users_repository.get_user(database, users["admin"]["user_id"])
        assert isinstance(user, UserModel)
        assert user.role == UserRole.ADMIN
        assert users_service.require_admin(database, user.user_id) is user
        assert database.in_transaction()
    assert not database.in_transaction()


@pytest.mark.parametrize(
    "username,status,code",
    [("learner", 403, "ROLE_NOT_ALLOWED"), ("missing", 404, "USER_NOT_FOUND")],
)
def test_upload_admin_check_keeps_role_errors(database, users, username, status, code):
    from app.core.exceptions import ApiError

    user_id = users[username]["user_id"] if username in users else 9223372036854775807
    with database.begin(), pytest.raises(ApiError) as caught:
        users_service.require_admin(database, user_id)
    assert caught.value.status_code == status and caught.value.code == code


def test_missing_user_is_not_found(client):
    response = client.get("/api/users/9223372036854775807")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "USER_NOT_FOUND"


@pytest.mark.parametrize("invalid", ["0", "-1", "abc", "9223372036854775808"])
def test_user_id_requires_positive_bigint(client, invalid):
    response = client.get(f"/api/users/{invalid}")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "context,path,result,expected_result",
    [
        ("VIDEO_END", "VIDEO_QUIZ", "CORRECT", "CORRECT"),
        ("FEED_REVIEW", "FEED_REVIEW", "WRONG", "WRONG"),
        ("WRONG_REVIEW", "WRONG_NOTE", "SKIPPED", "SKIP"),
    ],
)
def test_response_contract_and_read_has_no_side_effects(
    client, database, users, question, context, path, result, expected_result
):
    record = add_response(database, users, question, result=result, context=context)
    before = snapshot(database)
    url = f"/api/responses/{record['response_id']}"
    response = client.get(url, headers=headers(users))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data == {
        "response_id": record["response_id"],
        "attempt_id": str(record["attempt_id"]),
        "user_id": users["learner"]["user_id"],
        "question": {
            key: value
            for key, value in question.items()
            if key
            in {
                "question_id",
                "question_version_id",
                "content_id",
                "question_type",
                "question_text",
            }
        }
        | {
            "options": [
                {key: value for key, value in option.items() if key != "is_correct"}
                for option in question["options"]
            ]
        },
        "response_path": path,
        "result": expected_result,
        "selected_option_id": record["selected_option_id"],
        "correct_option_id": question["options"][1]["option_id"],
        "correct_answer": "보기2",
        "explanation": "제출 당시 해설",
        "submitted_at": "2026-10-15T03:06:00Z",
        "wrong_state": {
            "question_version_id": question["question_version_id"],
            "status": "PENDING",
            "wrong_count": 1,
            "resolved_at": None,
        }
        if result == "WRONG"
        else None,
    }
    assert [option["option_order"] for option in data["question"]["options"]] == [1, 2, 3]
    assert client.get(url, headers=headers(users)).json() == data
    assert snapshot(database) == before


def test_response_owner_and_admin_only(client, database, users, question):
    record = add_response(database, users, question)
    url = f"/api/responses/{record['response_id']}"
    owner = client.get(url, headers=headers(users))
    admin = client.get(url, headers=headers(users, "admin"))
    assert owner.status_code == admin.status_code == 200
    assert owner.json() == admin.json()
    foreign = client.get(url, headers=headers(users, "other"))
    absent = client.get("/api/responses/9223372036854775807", headers=headers(users))
    assert foreign.status_code == absent.status_code == 404
    assert foreign.json() == absent.json()
    assert foreign.json()["detail"]["code"] == "RESPONSE_NOT_FOUND"
    assert client.get(url).status_code == 422
    unknown = client.get(url, headers={"X-Actor-Id": "9223372036854775807"})
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["code"] == "USER_NOT_FOUND"


def test_unsubmitted_attempt_cannot_expose_answers(client, database, users, question):
    database.execute(
        text("""INSERT INTO sasu.quiz_attempts
                (attempt_id, user_id, learning_epoch, quiz_id, quiz_version_id, context)
                VALUES (:id, :user, 1, :question, :version, 'VIDEO_END')"""),
        {
            "id": uuid4(),
            "user": users["learner"]["user_id"],
            "question": question["question_id"],
            "version": question["question_version_id"],
        },
    )
    database.commit()
    before = snapshot(database)
    for username in ("learner", "admin"):
        response = client.get("/api/responses/1", headers=headers(users, username))
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "RESPONSE_NOT_FOUND"
        assert "correct_answer" not in response.text and "explanation" not in response.text
    assert snapshot(database) == before


@pytest.mark.parametrize("invalid", ["0", "-1", "abc", "9223372036854775808"])
def test_response_id_requires_positive_bigint(client, users, invalid):
    response = client.get(f"/api/responses/{invalid}", headers=headers(users))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_wrong_state_tracks_owner_and_submitted_version(client, database, users, question):
    record = add_response(database, users, question)
    url = f"/api/responses/{record['response_id']}"
    initial = client.get(url, headers=headers(users)).json()
    # 다른 학습자의 오답 횟수·해결 상태가 본인 상태에 섞이지 않는다.
    add_response(database, users, question, username="other")
    add_response(database, users, question, username="other")
    add_response(database, users, question, result="CORRECT", username="other")
    assert client.get(url, headers=headers(users)).json() == initial

    revised = client.post(
        f"/api/questions/{question['question_id']}/versions",
        headers=headers(users, "admin"),
        json={
            **question_body("OX"),
            "question_text": "수정된 문제",
            "explanation": "수정된 해설",
            "expected_current_version_id": question["question_version_id"],
        },
    )
    assert revised.status_code == 201, revised.text
    # 최신 버전 정답은 제출 버전의 오답 상태나 최초 결과를 바꾸지 않는다.
    add_response(database, users, revised.json(), result="CORRECT")
    assert client.get(url, headers=headers(users)).json() == initial
    add_response(database, users, question, result="CORRECT")
    resolved = client.get(url, headers=headers(users)).json()
    assert {key: value for key, value in resolved.items() if key != "wrong_state"} == {
        key: value for key, value in initial.items() if key != "wrong_state"
    }
    assert resolved["wrong_state"] == {
        "question_version_id": question["question_version_id"],
        "status": "RESOLVED",
        "wrong_count": 1,
        "resolved_at": "2026-10-15T03:06:00Z",
    }
    add_response(database, users, question)
    reopened = client.get(url, headers=headers(users)).json()
    assert reopened == {
        **initial,
        "wrong_state": {**initial["wrong_state"], "wrong_count": 2},
    }


def test_unavailable_content_does_not_hide_past_response(client, database, users, question):
    record = add_response(database, users, question, result="CORRECT")
    # 영상이 없고 DRAFT여서 현재 학습 조회는 막히지만 제출 결과는 볼 수 있다.
    current = client.get(f"/api/contents/{question['content_id']}/question", headers=headers(users))
    assert current.status_code == 404
    detail = client.get(f"/api/responses/{record['response_id']}", headers=headers(users))
    assert detail.status_code == 200
    assert detail.json()["question"]["question_version_id"] == question["question_version_id"]


@pytest.mark.parametrize("kind", ["OX", "MCQ_4"])
def test_response_question_type_and_options(client, database, users, question, kind):
    revised = client.post(
        f"/api/questions/{question['question_id']}/versions",
        headers=headers(users, "admin"),
        json={
            **question_body(kind),
            "expected_current_version_id": question["question_version_id"],
        },
    )
    assert revised.status_code == 201, revised.text
    record = add_response(database, users, revised.json(), result="CORRECT")
    detail = client.get(f"/api/responses/{record['response_id']}", headers=headers(users))
    assert detail.status_code == 200
    data = detail.json()
    assert data["question"]["question_type"] == kind
    assert len(data["question"]["options"]) == (2 if kind == "OX" else 4)
    assert data["correct_answer"] == ("X" if kind == "OX" else "보기2")
    assert all("is_correct" not in option for option in data["question"]["options"])


@pytest.mark.parametrize("path", ["/api/users", "/api/users/1", "/api/responses/1"])
def test_undefined_queries_are_rejected(client, users, path):
    response = client.get(path + "?page=1", headers=headers(users))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("target", ["list", "user", "response"])
def test_database_failures_are_not_successful_empty_results(client, users, monkeypatch, target):
    def fail(*args):
        raise OperationalError("private SQL", {}, Exception("secret connection"))

    module, name, url = {
        "list": (users_repository, "list_users", "/api/users"),
        "user": (users_repository, "find_user", f"/api/users/{users['learner']['user_id']}"),
        "response": (responses_repository, "find_response", "/api/responses/1"),
    }[target]
    monkeypatch.setattr(module, name, fail)
    response = client.get(url, headers=headers(users))
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_ERROR"
    assert "private" not in response.text and "secret" not in response.text
