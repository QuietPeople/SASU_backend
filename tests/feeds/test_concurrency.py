"""실제 PostgreSQL 잠금으로 CNT-01과 초기화 사이의 기록 세대 일관성을 검증한다."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.feeds import service
from app.modules.feeds.contracts import RankedFeedItem


@pytest.fixture
def database(postgres_engine):
    # 이 파일의 경합 검증만 임시 테스트 DB에 실제 커밋한다.
    with Session(postgres_engine) as session:
        yield session


def request_feed(client, records):
    return client.get(
        f"/api/users/{records['learner']}/feed",
        headers={"X-Actor-Id": str(records["learner"])},
    )


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
        assert not future.done(), "요청이 DB 잠금을 기다리지 않고 종료했습니다."
        time.sleep(0.01)
    raise AssertionError("PostgreSQL 잠금 대기를 확인하지 못했습니다.")


def commit_records(database, records, content):
    database.execute(
        text("UPDATE sasu.user_settings SET last_content_id = :content WHERE user_id = :user"),
        {"user": records["learner"], "content": content},
    )
    database.execute(
        text("""INSERT INTO sasu.watch_records
                (user_id, learning_epoch, content_id, first_played_at,
                 last_watched_at, completed_at, max_coverage_ratio)
                VALUES (:user, 1, :content, now(), now(), now(), 0.95)"""),
        {"user": records["learner"], "content": content},
    )
    database.execute(
        text(
            "INSERT INTO sasu.content_likes (user_id, learning_epoch, content_id) "
            "VALUES (:user, 1, :content)"
        ),
        {"user": records["learner"], "content": content},
    )
    database.commit()


def test_feed_waits_for_reset_and_uses_new_generation(
    postgres_engine, database, records, content_factory, http_factory, monkeypatch
):
    content = content_factory()
    commit_records(database, records, content)
    original = service.current_epoch
    entered, backend = Event(), {}

    def observe(session, *args, **kwargs):
        backend["pid"] = session.scalar(text("SELECT pg_backend_pid()"))
        entered.set()
        return original(session, *args, **kwargs)

    monkeypatch.setattr(service, "current_epoch", observe)
    captured = []

    def rank(context):
        captured.append(context)
        return [
            RankedFeedItem(item.content_id, "LATEST", "연결 확인") for item in context.candidates
        ]

    with Session(postgres_engine) as resetting, http_factory(postgres_engine) as client:
        client.app.dependency_overrides[service.get_feed_ranker] = lambda: rank
        resetting.scalar(text("SELECT sasu.reset_learning(:id, 1)"), {"id": records["learner"]})
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(request_feed, client, records)
            try:
                wait_for_lock(postgres_engine, entered, backend, pending)
                resetting.commit()
                response = pending.result(timeout=5)
            finally:
                resetting.rollback()
    assert response.status_code == 200, response.text
    assert response.json()["record_generation"] == 1
    summary = next(
        item["content"]
        for item in response.json()["items"]
        if item["content"]["content_id"] == content
    )
    assert summary["liked"] is summary["watch_completed"] is False
    assert captured[0].resume_content_id is None
    assert captured[0].recent_watched_tag_ids == frozenset()
    assert not next(item.watched for item in captured[0].candidates if item.content_id == content)


def test_reset_waits_until_feed_response_is_built(
    postgres_engine, database, records, content_factory, http_factory
):
    content = content_factory()
    commit_records(database, records, content)
    reading, release, reset_entered = Event(), Event(), Event()
    backend = {}

    def rank(context):
        assert context.resume_content_id == content
        assert next(item.watched for item in context.candidates if item.content_id == content)
        reading.set()
        assert release.wait(timeout=5)
        return [
            RankedFeedItem(item.content_id, "LATEST", "연결 확인") for item in context.candidates
        ]

    def reset():
        with postgres_engine.begin() as connection:
            backend["pid"] = connection.scalar(text("SELECT pg_backend_pid()"))
            reset_entered.set()
            return connection.scalar(
                text("SELECT sasu.reset_learning(:id, 1)"), {"id": records["learner"]}
            )

    with http_factory(postgres_engine) as client:
        client.app.dependency_overrides[service.get_feed_ranker] = lambda: rank
        with ThreadPoolExecutor(max_workers=2) as executor:
            read = executor.submit(request_feed, client, records)
            try:
                assert reading.wait(timeout=5)
                resetting = executor.submit(reset)
                wait_for_lock(postgres_engine, reset_entered, backend, resetting)
                release.set()
                response = read.result(timeout=5)
                assert resetting.result(timeout=5) == 2
            finally:
                release.set()
        assert response.status_code == 200, response.text
        assert response.json()["record_generation"] == 0
        summary = next(
            item["content"]
            for item in response.json()["items"]
            if item["content"]["content_id"] == content
        )
        assert summary["liked"] is summary["watch_completed"] is True
        client.app.dependency_overrides.pop(service.get_feed_ranker)
        refreshed = request_feed(client, records)
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["record_generation"] == 1
