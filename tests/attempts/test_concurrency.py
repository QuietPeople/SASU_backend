"""서로 다른 연결과 PostgreSQL의 실제 잠금 대기로 재전송·초기화·편집 경합 검증."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.attempts import repository
from app.modules.questions import repository as questions_repository
from app.modules.questions.schemas import QuestionInput
from app.modules.users import settings_repository


def request_for(records):
    question = records["questions"][0]
    return {
        "attempt_id": str(uuid4()),
        "question_id": question["question_id"],
        "expected_question_version_id": question["question_version_id"],
        "response_path": "VIDEO_QUIZ",
    }


def post(client, records, request, user="learner"):
    return client.post(
        f"/api/users/{records[user]}/question-attempts",
        headers={"X-Actor-Id": str(records[user]), "X-Record-Generation": "0"},
        json=request,
    )


def hold_attempt(session, records, request):
    settings_repository.lock_settings(session, records["learner"], write=True)
    repository.lock_attempt_id(session, request["attempt_id"])
    repository.insert_attempt(
        session,
        request["attempt_id"],
        records["learner"],
        1,
        request["question_id"],
        request["expected_question_version_id"],
        "VIDEO_END",
    )


def observe(monkeypatch, name):
    entered, backend = Event(), {}
    owner = settings_repository if name == "lock_settings" else repository
    original = getattr(owner, name)

    def tracked(session, *args, **kwargs):
        backend["pid"] = session.scalar(text("SELECT pg_backend_pid()"))
        entered.set()
        return original(session, *args, **kwargs)

    monkeypatch.setattr(owner, name, tracked)
    return entered, backend


def wait_for_lock(engine, entered, backend, future):
    assert entered.wait(timeout=5)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with engine.connect() as connection:
            wait = connection.scalar(
                text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                {"pid": backend["pid"]},
            )
        if wait == "Lock":
            assert not future.done()
            return
        assert not future.done(), "요청이 실제 DB 잠금을 기다리지 않고 종료했습니다."
        time.sleep(0.01)
    raise AssertionError("PostgreSQL 잠금 대기를 확인하지 못했습니다.")


def test_same_attempt_uuid_waits_then_returns_original(
    postgres_engine, committed_records, http_factory, monkeypatch
):
    records = committed_records
    request = request_for(records)
    with Session(postgres_engine) as first, http_factory(postgres_engine) as client:
        hold_attempt(first, records, request)
        entered, backend = observe(monkeypatch, "lock_settings")
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(post, client, records, request)
            try:
                wait_for_lock(postgres_engine, entered, backend, pending)
                first.commit()
                response = pending.result(timeout=5)
            finally:
                first.rollback()
        assert response.status_code == 200, response.text
        assert response.json()["attempt_id"] == request["attempt_id"]
        assert (
            first.scalar(
                text("SELECT count(*) FROM sasu.quiz_attempts WHERE attempt_id = :id"),
                {"id": request["attempt_id"]},
            )
            == 1
        )


def test_different_users_cannot_race_to_reuse_uuid(
    postgres_engine, committed_records, http_factory, monkeypatch
):
    records = committed_records
    request = request_for(records)
    with Session(postgres_engine) as first, http_factory(postgres_engine) as client:
        hold_attempt(first, records, request)
        entered, backend = observe(monkeypatch, "lock_attempt_id")
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(post, client, records, request, "other")
            try:
                wait_for_lock(postgres_engine, entered, backend, pending)
                first.commit()
                response = pending.result(timeout=5)
            finally:
                first.rollback()
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ATTEMPT_ID_CONFLICT"


def test_reset_commits_first_and_rejects_late_create(
    postgres_engine, committed_records, http_factory, monkeypatch
):
    records = committed_records
    request = request_for(records)
    with Session(postgres_engine) as first, http_factory(postgres_engine) as client:
        first.scalar(text("SELECT sasu.reset_learning(:id, 1)"), {"id": records["learner"]})
        entered, backend = observe(monkeypatch, "lock_settings")
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(post, client, records, request)
            try:
                wait_for_lock(postgres_engine, entered, backend, pending)
                first.commit()
                response = pending.result(timeout=5)
            finally:
                first.rollback()
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "RECORD_GENERATION_MISMATCH"
        assert (
            first.scalar(
                text("SELECT count(*) FROM sasu.quiz_attempts WHERE user_id = :id"),
                {"id": records["learner"]},
            )
            == 0
        )


def test_create_commits_first_then_reset_removes_attempt(postgres_engine, committed_records):
    records = committed_records
    request = request_for(records)
    entered, backend = Event(), {}

    def reset():
        with postgres_engine.begin() as connection:
            backend["pid"] = connection.scalar(text("SELECT pg_backend_pid()"))
            entered.set()
            return connection.scalar(
                text("SELECT sasu.reset_learning(:id, 1)"), {"id": records["learner"]}
            )

    with Session(postgres_engine) as first:
        hold_attempt(first, records, request)
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(reset)
            try:
                wait_for_lock(postgres_engine, entered, backend, pending)
                first.commit()
                assert pending.result(timeout=5) == 2
            finally:
                first.rollback()
        assert repository.find_attempt(first, request["attempt_id"]) is None


def test_revision_commits_before_create_version_check(
    postgres_engine, committed_records, http_factory, monkeypatch
):
    records = committed_records
    request = request_for(records)
    update = QuestionInput(
        question_type="OX",
        question_text="편집 후 문항",
        explanation="편집 후 해설",
        options=[
            {"option_order": 1, "option_text": "O", "is_correct": True},
            {"option_order": 2, "option_text": "X", "is_correct": False},
        ],
    )
    with Session(postgres_engine) as first, http_factory(postgres_engine) as client:
        questions_repository.find_question(first, request["question_id"], lock=True)
        version = questions_repository.create_version(first, request["question_id"], 2, update)
        questions_repository.create_options(first, version, update.options)
        questions_repository.set_current_version(first, request["question_id"], version)
        entered, backend = observe(monkeypatch, "lock_question")
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(post, client, records, request)
            try:
                wait_for_lock(postgres_engine, entered, backend, pending)
                first.commit()
                response = pending.result(timeout=5)
            finally:
                first.rollback()
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "VERSION_CONFLICT"


def seed_submission_attempt(session, records):
    request = request_for(records)
    repository.insert_attempt(
        session,
        request["attempt_id"],
        records["learner"],
        1,
        request["question_id"],
        request["expected_question_version_id"],
        "VIDEO_END",
    )
    session.execute(
        text("""INSERT INTO sasu.learning_events
                (event_id, user_id, learning_epoch, event_type,
                 content_id, quiz_version_id, attempt_id)
                VALUES (:event, :user, 1, 'QUIZ_DISPLAYED', :content, :version, :attempt)"""),
        {
            "event": uuid4(),
            "user": records["learner"],
            "content": records["questions"][0]["content_id"],
            "version": request["expected_question_version_id"],
            "attempt": request["attempt_id"],
        },
    )
    session.commit()
    return request["attempt_id"]


def hold_wrong_response(session, records, attempt_id):
    settings_repository.lock_settings(session, records["learner"], write=True)
    repository.lock_owned_attempt(session, attempt_id, records["learner"], 1)
    question = records["questions"][0]
    return repository.insert_response(
        session,
        attempt_id,
        question["question_version_id"],
        question["options"][1]["option_id"],
        "WRONG",
    )


def put_response(client, records, attempt_id, payload):
    return client.put(
        f"/api/users/{records['learner']}/question-attempts/{attempt_id}/response",
        headers={"X-Actor-Id": str(records["learner"]), "X-Record-Generation": "0"},
        json=payload,
    )


@pytest.mark.parametrize("retry", ["same", "different_option", "skip"])
def test_concurrent_submission_waits_and_preserves_first_verdict(
    postgres_engine, committed_records, http_factory, monkeypatch, retry
):
    records = committed_records
    with Session(postgres_engine) as first, http_factory(postgres_engine) as client:
        attempt_id = seed_submission_attempt(first, records)
        response_id = hold_wrong_response(first, records, attempt_id)
        payload = (
            {"action": "SKIP"}
            if retry == "skip"
            else {
                "action": "ANSWER",
                "selected_option_id": records["questions"][0]["options"][
                    1 if retry == "same" else 0
                ]["option_id"],
            }
        )
        entered, backend = observe(monkeypatch, "lock_settings")
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(put_response, client, records, attempt_id, payload)
            try:
                wait_for_lock(postgres_engine, entered, backend, pending)
                first.commit()
                response = pending.result(timeout=5)
            finally:
                first.rollback()
        if retry == "same":
            assert response.status_code == 200, response.text
            assert response.json()["response_id"] == response_id
            assert response.json()["result"] == "WRONG"
        else:
            assert response.status_code == 409, response.text
            assert response.json()["detail"]["code"] == "ALREADY_SUBMITTED"
        assert (
            first.scalar(
                text("SELECT wrong_count FROM sasu.wrong_answers WHERE user_id = :id"),
                {"id": records["learner"]},
            )
            == 1
        )
        assert (
            first.scalar(
                text("SELECT count(*) FROM sasu.quiz_responses WHERE attempt_id = :id"),
                {"id": attempt_id},
            )
            == 1
        )


def test_distinct_attempts_concurrently_increment_wrong_once_each(
    postgres_engine, committed_records, http_factory, monkeypatch
):
    records = committed_records
    with Session(postgres_engine) as first, http_factory(postgres_engine) as client:
        original = seed_submission_attempt(first, records)
        second = seed_submission_attempt(first, records)
        hold_wrong_response(first, records, original)
        payload = {
            "action": "ANSWER",
            "selected_option_id": records["questions"][0]["options"][1]["option_id"],
        }
        entered, backend = observe(monkeypatch, "lock_settings")
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(put_response, client, records, second, payload)
            try:
                wait_for_lock(postgres_engine, entered, backend, pending)
                first.commit()
                response = pending.result(timeout=5)
            finally:
                first.rollback()
        assert response.status_code == 200, response.text
        assert response.json()["wrong_state"]["wrong_count"] == 2
        assert (
            first.scalar(
                text("SELECT wrong_count FROM sasu.wrong_answers WHERE user_id = :id"),
                {"id": records["learner"]},
            )
            == 2
        )


def test_reset_commits_before_late_submission(
    postgres_engine, committed_records, http_factory, monkeypatch
):
    records = committed_records
    with Session(postgres_engine) as first, http_factory(postgres_engine) as client:
        attempt_id = seed_submission_attempt(first, records)
        first.scalar(text("SELECT sasu.reset_learning(:user, 1)"), {"user": records["learner"]})
        entered, backend = observe(monkeypatch, "lock_settings")
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(put_response, client, records, attempt_id, {"action": "SKIP"})
            try:
                wait_for_lock(postgres_engine, entered, backend, pending)
                first.commit()
                response = pending.result(timeout=5)
            finally:
                first.rollback()
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "RECORD_GENERATION_MISMATCH"
        assert repository.find_attempt(first, attempt_id) is None


def test_reset_waits_for_submission_then_clears_response_and_wrong(
    postgres_engine, committed_records
):
    records = committed_records
    entered, backend = Event(), {}

    def reset():
        with postgres_engine.begin() as connection:
            backend["pid"] = connection.scalar(text("SELECT pg_backend_pid()"))
            entered.set()
            return connection.scalar(
                text("SELECT sasu.reset_learning(:id, 1)"), {"id": records["learner"]}
            )

    with Session(postgres_engine) as first:
        attempt_id = seed_submission_attempt(first, records)
        response_id = hold_wrong_response(first, records, attempt_id)
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(reset)
            try:
                wait_for_lock(postgres_engine, entered, backend, pending)
                first.commit()
                assert pending.result(timeout=5) == 2
            finally:
                first.rollback()
        assert repository.find_attempt(first, attempt_id) is None
        assert (
            first.scalar(
                text("SELECT count(*) FROM sasu.quiz_responses WHERE response_id = :id"),
                {"id": response_id},
            )
            == 0
        )
        assert (
            first.scalar(
                text("SELECT count(*) FROM sasu.wrong_answers WHERE user_id = :id"),
                {"id": records["learner"]},
            )
            == 0
        )


def test_submission_waits_for_display_event_commit(
    postgres_engine, committed_records, http_factory, monkeypatch
):
    records = committed_records
    request = request_for(records)
    with Session(postgres_engine) as first, http_factory(postgres_engine) as client:
        repository.insert_attempt(
            first,
            request["attempt_id"],
            records["learner"],
            1,
            request["question_id"],
            request["expected_question_version_id"],
            "VIDEO_END",
        )
        first.commit()
        first.execute(
            text("""INSERT INTO sasu.learning_events
                    (event_id, user_id, learning_epoch, event_type,
                     content_id, quiz_version_id, attempt_id)
                    VALUES (:event, :user, 1, 'QUIZ_DISPLAYED', :content, :version, :attempt)"""),
            {
                "event": uuid4(),
                "user": records["learner"],
                "content": records["questions"][0]["content_id"],
                "version": request["expected_question_version_id"],
                "attempt": request["attempt_id"],
            },
        )
        entered, backend = observe(monkeypatch, "lock_settings")
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(
                put_response, client, records, request["attempt_id"], {"action": "SKIP"}
            )
            try:
                wait_for_lock(postgres_engine, entered, backend, pending)
                first.commit()
                response = pending.result(timeout=5)
            finally:
                first.rollback()
        assert response.status_code == 200, response.text
        assert response.json()["result"] == "SKIP"
