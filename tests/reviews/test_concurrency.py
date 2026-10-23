"""실제 PostgreSQL 잠금 대기로 복습 조회와 초기화·채점의 일관성을 검증한다."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.attempts import repository as attempts_repository
from app.modules.reviews import repository, service


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
        assert not future.done(), "조회·초기화 요청이 DB 잠금을 기다리지 않고 종료했습니다."
        time.sleep(0.01)
    raise AssertionError("PostgreSQL 잠금 대기를 확인하지 못했습니다.")


def prepare_watch(session, records):
    session.execute(
        text("""INSERT INTO sasu.watch_records
                (user_id, learning_epoch, content_id, first_played_at, last_watched_at,
                 completed_at, max_coverage_ratio)
                VALUES (:user, 1, :content, now(), now(), now(), 0.9)"""),
        {"user": records["learner"], "content": records["questions"][0]["content_id"]},
    )
    session.commit()


def candidate(client, records):
    return client.post(
        f"/api/users/{records['learner']}/reviews/feed/candidate",
        headers={"X-Actor-Id": str(records["learner"])},
        json={"shown_question_version_ids": [], "retry_question_version_ids": []},
    )


def observe_state(monkeypatch):
    entered, backend = Event(), {}
    original = service.current_epoch

    def observe(session, *args, **kwargs):
        backend["pid"] = session.scalar(text("SELECT pg_backend_pid()"))
        entered.set()
        return original(session, *args, **kwargs)

    monkeypatch.setattr(service, "current_epoch", observe)
    return entered, backend


def test_candidate_waits_for_reset_and_uses_new_generation(
    postgres_engine, committed_records, http_factory, monkeypatch
):
    records = committed_records
    with Session(postgres_engine) as first, http_factory(postgres_engine) as client:
        prepare_watch(first, records)
        first.scalar(text("SELECT sasu.reset_learning(:id, 1)"), {"id": records["learner"]})
        entered, backend = observe_state(monkeypatch)
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(candidate, client, records)
            try:
                wait_for_lock(postgres_engine, entered, backend, pending)
                first.commit()
                response = pending.result(timeout=5)
            finally:
                first.rollback()
        assert response.status_code == 200, response.text
        assert response.json() == {"candidate": None, "record_generation": 1}


def test_reset_waits_for_candidate_read_to_finish(
    postgres_engine, committed_records, http_factory, monkeypatch
):
    records = committed_records
    reading, release, reset_entered = Event(), Event(), Event()
    backend = {}
    original = repository.feed_candidates

    def pause(*args, **kwargs):
        rows = original(*args, **kwargs)
        reading.set()
        assert release.wait(timeout=5)
        return rows

    def reset():
        with postgres_engine.begin() as connection:
            backend["pid"] = connection.scalar(text("SELECT pg_backend_pid()"))
            reset_entered.set()
            return connection.scalar(
                text("SELECT sasu.reset_learning(:id, 1)"), {"id": records["learner"]}
            )

    monkeypatch.setattr(repository, "feed_candidates", pause)
    with Session(postgres_engine) as first, http_factory(postgres_engine) as client:
        prepare_watch(first, records)
        with ThreadPoolExecutor(max_workers=2) as executor:
            read = executor.submit(candidate, client, records)
            try:
                assert reading.wait(timeout=5)
                pending_reset = executor.submit(reset)
                wait_for_lock(postgres_engine, reset_entered, backend, pending_reset)
                release.set()
                response = read.result(timeout=5)
                assert pending_reset.result(timeout=5) == 2
            finally:
                release.set()
        assert response.status_code == 200, response.text
        assert response.json()["record_generation"] == 0
        assert response.json()["candidate"]["content_id"] == records["questions"][0]["content_id"]
        assert candidate(client, records).json() == {"candidate": None, "record_generation": 1}


def test_wrong_list_waits_for_grading_and_reads_committed_wrong_state(
    postgres_engine, committed_records, http_factory, monkeypatch
):
    records = committed_records
    question = records["questions"][0]
    with Session(postgres_engine) as first, http_factory(postgres_engine) as client:
        attempts_repository.learner_epoch(first, records["learner"], write=True)
        attempt_id = uuid4()
        attempts_repository.insert_attempt(
            first,
            attempt_id,
            records["learner"],
            1,
            question["question_id"],
            question["question_version_id"],
            "FEED_REVIEW",
        )
        attempts_repository.insert_response(
            first,
            attempt_id,
            question["question_version_id"],
            question["options"][1]["option_id"],
            "WRONG",
        )
        entered, backend = observe_state(monkeypatch)
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(
                client.get,
                f"/api/users/{records['learner']}/reviews/wrong-answers",
                headers={"X-Actor-Id": str(records["learner"])},
            )
            try:
                wait_for_lock(postgres_engine, entered, backend, pending)
                first.commit()
                response = pending.result(timeout=5)
            finally:
                first.rollback()
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["wrong_count"] == 1
        assert response.json()["items"][0]["status"] == "PENDING"
