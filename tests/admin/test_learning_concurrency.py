"""별도 연결의 실제 커밋·행 잠금으로 관리자 편집 경합을 검증한다."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.modules.curricula import repository as curricula_repository
from app.modules.questions import repository as questions_repository
from app.modules.questions.schemas import QuestionInput

BODY = {
    "question_type": "OX",
    "question_text": "문제",
    "explanation": "해설",
    "options": [
        {"option_order": 1, "option_text": "O", "is_correct": True},
        {"option_order": 2, "option_text": "X", "is_correct": False},
    ],
}


@pytest.fixture
def records(postgres_engine):
    # 이 파일 전용 테스트 DB에만 커밋하며, 마지막에 해당 DB 전체를 정리한다.
    with postgres_engine.begin() as connection:
        admin = connection.scalar(
            text("""INSERT INTO sasu.app_users (username, display_name, role)
                    VALUES (:name, '동시성 관리자', 'ADMIN') RETURNING user_id"""),
            {"name": uuid4().hex},
        )
        contents = [
            connection.scalar(
                text(
                    "INSERT INTO sasu.contents (created_by_user_id) "
                    "VALUES (:id) RETURNING content_id"
                ),
                {"id": admin},
            )
            for _ in range(2)
        ]
        curriculum = connection.scalar(
            text("INSERT INTO sasu.curricula (title) VALUES ('과정') RETURNING curriculum_id")
        )
    return {"admin": admin, "contents": contents, "curriculum": curriculum}


@pytest.fixture
def http(postgres_engine):
    def concurrent_session():
        with Session(postgres_engine) as session:
            session.execute(text("SET LOCAL lock_timeout = '5s'"))
            yield session

    app.dependency_overrides[get_db] = concurrent_session
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def observe_lock(monkeypatch, repository, name):
    entered = Event()
    original = getattr(repository, name)

    def observed(*args, **kwargs):
        if kwargs.get("lock"):
            entered.set()
        return original(*args, **kwargs)

    monkeypatch.setattr(repository, name, observed)
    return entered


def commit_then_wait(first, entered, pending):
    try:
        assert entered.wait(timeout=5)
        assert not pending.done()
        first.commit()
        return pending.result(timeout=5)
    finally:
        first.rollback()


def write_version(session, question_id, number, payload):
    version = questions_repository.create_version(session, question_id, number, payload)
    questions_repository.create_options(session, version, payload.options)
    questions_repository.set_current_version(session, question_id, version)
    return version


def test_first_registration_is_serialized(http, records, postgres_engine, monkeypatch):
    content = records["contents"][0]
    payload = QuestionInput.model_validate(BODY)
    with Session(postgres_engine) as first:
        questions_repository.find_content(first, content, lock=True)
        question = questions_repository.create_question(first, content)
        write_version(first, question, 1, payload)
        entered = observe_lock(monkeypatch, questions_repository, "find_content")
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(
                http.post,
                f"/api/contents/{content}/question",
                headers={"X-Actor-Id": str(records["admin"])},
                json=BODY,
            )
            response = commit_then_wait(first, entered, pending)
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "QUESTION_ALREADY_EXISTS"
        assert (
            first.scalar(
                text("SELECT count(*) FROM sasu.quizzes WHERE content_id = :id"), {"id": content}
            )
            == 1
        )


def test_stale_version_waits_then_reports_conflict(http, records, postgres_engine, monkeypatch):
    actor = {"X-Actor-Id": str(records["admin"])}
    initial = http.post(
        f"/api/contents/{records['contents'][0]}/question", headers=actor, json=BODY
    )
    assert initial.status_code == 201, initial.text
    initial = initial.json()
    with Session(postgres_engine) as first:
        question = initial["question_id"]
        questions_repository.find_question(first, question, lock=True)
        expected_new = write_version(first, question, 2, QuestionInput.model_validate(BODY))
        entered = observe_lock(monkeypatch, questions_repository, "find_question")
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(
                http.post,
                f"/api/questions/{question}/versions",
                headers=actor,
                json={**BODY, "expected_current_version_id": initial["question_version_id"]},
            )
            response = commit_then_wait(first, entered, pending)
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "VERSION_CONFLICT"
        assert (
            first.scalar(
                text("SELECT current_version_id FROM sasu.quizzes WHERE quiz_id = :id"),
                {"id": question},
            )
            == expected_new
        )
        assert (
            first.scalar(
                text("SELECT count(*) FROM sasu.quiz_versions WHERE quiz_id = :id"),
                {"id": question},
            )
            == 2
        )


def test_course_replacements_are_serialized(http, records, postgres_engine, monkeypatch):
    path = f"/api/curriculums/{records['curriculum']}/steps"
    actor = {"X-Actor-Id": str(records["admin"])}
    assert (
        http.put(path, headers=actor, json={"content_ids": records["contents"]}).status_code == 200
    )
    with Session(postgres_engine) as first:
        curricula_repository.find_curriculum(first, records["curriculum"], lock=True)
        curricula_repository.replace_steps(first, records["curriculum"], records["contents"][::-1])
        entered = observe_lock(monkeypatch, curricula_repository, "find_curriculum")
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(
                http.put, path, headers=actor, json={"content_ids": records["contents"][:1]}
            )
            response = commit_then_wait(first, entered, pending)
        assert response.status_code == 200, response.text
        assert [step["content_id"] for step in response.json()["items"]] == records["contents"][:1]
        final = http.get(path + "?view=editor", headers=actor)
        assert final.json() == response.json()
