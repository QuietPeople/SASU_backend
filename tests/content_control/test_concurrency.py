from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.router import api_router
from app.core.exceptions import register_exception_handlers
from app.db.models import load_models
from app.db.session import get_db
from app.modules.contents import deletion_repository, repository
from app.modules.curricula.repository import replace_steps
from tests.attempts.conftest import seed_records


@pytest.fixture
def state(postgres_engine):
    load_models()
    with Session(postgres_engine) as session:
        records = seed_records(session)
    application = FastAPI()
    register_exception_handlers(application)
    application.include_router(api_router)

    def database():
        with Session(postgres_engine) as session:
            yield session

    application.dependency_overrides[get_db] = database
    with TestClient(application, raise_server_exceptions=False) as client:
        question = records["questions"][0]
        headers = {"X-Actor-Id": str(records["admin"])}
        path = f"/api/contents/{question['content_id']}"
        detail = client.get(path + "?view=editor", headers=headers).json()
        yield client, records, path, headers, detail["updated_at"]


def test_delete_waits_for_inflight_learning_transaction(state, postgres_engine, monkeypatch):
    client, records, path, headers, version = state
    started = Event()
    original = repository.get_content_for_update

    def lock(session, content_id):
        started.set()
        return original(session, content_id)

    monkeypatch.setattr(repository, "get_content_for_update", lock)
    with Session(postgres_engine) as learner, ThreadPoolExecutor(1) as pool:
        learner.execute(
            text("SELECT user_id FROM sasu.user_settings WHERE user_id=:id FOR UPDATE"),
            {"id": records["learner"]},
        )
        learner.execute(
            text("SELECT content_id FROM sasu.contents WHERE content_id=:id FOR SHARE"),
            {"id": records["questions"][0]["content_id"]},
        )
        deletion = pool.submit(
            client.request,
            "DELETE",
            path,
            headers=headers,
            json={"expected_updated_at": version, "confirm": True},
        )
        assert started.wait(5)
        try:
            with pytest.raises(TimeoutError):
                deletion.result(timeout=0.15)
            # 대상 콘텐츠의 처리 완료를 기다려도 관계없는 학습자의 요청은 막지 않는다.
            with Session(postgres_engine) as unrelated:
                unrelated.execute(text("SET LOCAL lock_timeout = '200ms'"))
                unrelated.execute(
                    text("SELECT user_id FROM sasu.user_settings WHERE user_id=:id FOR UPDATE"),
                    {"id": records["other"]},
                )
            learner.execute(
                text("""INSERT INTO sasu.content_likes(user_id, learning_epoch, content_id)
                    VALUES (:user, 1, :content)"""),
                {"user": records["learner"], "content": records["questions"][0]["content_id"]},
            )
        finally:
            learner.commit()
        response = deletion.result(timeout=10)
        assert response.status_code == 200, response.text
    with Session(postgres_engine) as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM sasu.content_likes WHERE content_id=:id"),
                {"id": records["questions"][0]["content_id"]},
            )
            == 0
        )


def test_learning_request_after_delete_cannot_recreate_orphan_records(state, monkeypatch):
    client, records, path, headers, version = state
    deleted, release = Event(), Event()
    original = deletion_repository.delete_owned_rows

    def hold(session, content):
        files = original(session, content)
        deleted.set()
        assert release.wait(10)
        return files

    monkeypatch.setattr(deletion_repository, "delete_owned_rows", hold)
    question = records["questions"][0]
    with ThreadPoolExecutor(2) as pool:
        deletion = pool.submit(
            client.request,
            "DELETE",
            path,
            headers=headers,
            json={"expected_updated_at": version, "confirm": True},
        )
        assert deleted.wait(5)
        attempt = pool.submit(
            client.post,
            f"/api/users/{records['learner']}/question-attempts",
            headers={"X-Actor-Id": str(records["learner"]), "X-Record-Generation": "0"},
            json={
                "attempt_id": str(uuid4()),
                "question_id": question["question_id"],
                "expected_question_version_id": question["question_version_id"],
                "response_path": "VIDEO_QUIZ",
            },
        )
        try:
            with pytest.raises(TimeoutError):
                attempt.result(timeout=0.15)
        finally:
            release.set()
        assert deletion.result(timeout=10).status_code == 200
        response = attempt.result(timeout=10)
        assert response.status_code == 404, response.text


def test_concurrent_deletes_only_one_succeeds(state):
    client, records, path, headers, version = state
    with ThreadPoolExecutor(2) as pool:
        futures = [
            pool.submit(
                client.request,
                "DELETE",
                path,
                headers=headers,
                json={"expected_updated_at": version, "confirm": True},
            )
            for _ in range(2)
        ]
        assert sorted(future.result(timeout=10).status_code for future in futures) == [200, 404]


@pytest.mark.parametrize("reference", ["position", "old_attempt", "event"])
def test_busy_related_learner_rejects_delete_and_allows_retry(state, postgres_engine, reference):
    client, records, path, headers, version = state
    question = records["questions"][0]
    params = {
        "user": records["learner"],
        "content": question["content_id"],
        "quiz": question["question_id"],
        "version": question["question_version_id"],
        "id": uuid4(),
    }
    with Session(postgres_engine) as session:
        if reference == "position":
            session.execute(
                text("UPDATE sasu.user_settings SET last_content_id=:content WHERE user_id=:user"),
                params,
            )
        elif reference == "old_attempt":
            session.execute(
                text("""INSERT INTO sasu.quiz_attempts
                    (attempt_id, user_id, learning_epoch, quiz_id, quiz_version_id, context)
                    VALUES (:id, :user, 1, :quiz, :version, 'VIDEO_END')"""),
                params,
            )
            session.execute(
                text("UPDATE sasu.user_settings SET learning_epoch=2 WHERE user_id=:user"), params
            )
        else:
            session.execute(
                text("""INSERT INTO sasu.learning_events
                    (event_id, user_id, learning_epoch, event_type, content_id, quiz_version_id)
                    VALUES (:id, :user, 1, 'CARD_OPENED', :content, :version)"""),
                params,
            )
        session.commit()

    with Session(postgres_engine) as learner, ThreadPoolExecutor(1) as pool:
        learner.execute(
            text("SELECT user_id FROM sasu.user_settings WHERE user_id=:user FOR UPDATE"), params
        )
        response = pool.submit(
            client.request,
            "DELETE",
            path,
            headers=headers,
            json={"expected_updated_at": version, "confirm": True},
        ).result(timeout=5)
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "CONTENT_IN_USE"
        # 삭제가 먼저 잡았던 콘텐츠 잠금도 풀려 학습 요청이 계속 진행될 수 있다.
        assert (
            learner.scalar(
                text(
                    "SELECT content_id FROM sasu.contents "
                    "WHERE content_id=:content FOR SHARE NOWAIT"
                ),
                params,
            )
            == question["content_id"]
        )
        learner.commit()
    assert client.get(path + "?view=editor", headers=headers).json()["updated_at"] == version
    response = client.request(
        "DELETE", path, headers=headers, json={"expected_updated_at": version, "confirm": True}
    )
    assert response.status_code == 200, response.text


def create_series(engine, content_ids):
    with Session(engine) as session:
        series_id = session.scalar(
            text("INSERT INTO sasu.curricula(title) VALUES ('동시 편성') RETURNING curriculum_id")
        )
        replace_steps(session, series_id, content_ids)
        session.commit()
        return series_id


def test_busy_series_rejects_delete_without_losing_updated_order(state, postgres_engine):
    client, records, path, headers, version = state
    ids = [q["content_id"] for q in records["questions"]]
    series_id = create_series(postgres_engine, ids)
    with Session(postgres_engine) as editor, ThreadPoolExecutor(1) as pool:
        editor.execute(
            text("SELECT curriculum_id FROM sasu.curricula WHERE curriculum_id=:id FOR UPDATE"),
            {"id": series_id},
        )
        response = pool.submit(
            client.request,
            "DELETE",
            path,
            headers=headers,
            json={"expected_updated_at": version, "confirm": True},
        ).result(timeout=5)
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "CONTENT_IN_USE"
        # 충돌 후 진행된 편성 순서를 재시도에서 유지하고 삭제 대상만 제외한다.
        replace_steps(editor, series_id, [ids[2], ids[0], ids[1]])
        editor.commit()
    response = client.request(
        "DELETE", path, headers=headers, json={"expected_updated_at": version, "confirm": True}
    )
    assert response.status_code == 200, response.text
    with Session(postgres_engine) as session:
        rows = session.execute(
            text("""SELECT content_id, position FROM sasu.curriculum_items
                WHERE curriculum_id=:id ORDER BY position"""),
            {"id": series_id},
        ).all()
        assert rows == [(ids[2], 1), (ids[1], 2)]


def test_deleting_content_does_not_block_unrelated_learning_or_series(
    state, postgres_engine, monkeypatch
):
    client, records, path, headers, version = state
    target, _, other = [q["content_id"] for q in records["questions"]]
    related_series = create_series(postgres_engine, [target, other])
    unrelated_series = create_series(postgres_engine, [other])
    with Session(postgres_engine) as session:
        session.execute(
            text("UPDATE sasu.user_settings SET last_content_id=:cid WHERE user_id=:uid"),
            {"cid": target, "uid": records["learner"]},
        )
        session.commit()
    deleting, release = Event(), Event()
    original = deletion_repository.delete_owned_rows

    def hold(session, content):
        files = original(session, content)
        deleting.set()
        assert release.wait(10)
        return files

    monkeypatch.setattr(deletion_repository, "delete_owned_rows", hold)
    with ThreadPoolExecutor(1) as pool:
        deletion = pool.submit(
            client.request,
            "DELETE",
            path,
            headers=headers,
            json={"expected_updated_at": version, "confirm": True},
        )
        assert deleting.wait(5)
        try:
            with Session(postgres_engine) as unrelated:
                unrelated.execute(text("SET LOCAL lock_timeout = '200ms'"))
                unrelated.execute(
                    text("SELECT user_id FROM sasu.user_settings WHERE user_id=:id FOR UPDATE"),
                    {"id": records["other"]},
                )
                unrelated.execute(
                    text("SELECT content_id FROM sasu.contents WHERE content_id=:id FOR SHARE"),
                    {"id": other},
                )
                unrelated.execute(
                    text("""INSERT INTO sasu.content_likes(user_id, learning_epoch, content_id)
                        VALUES (:uid, 1, :cid)"""),
                    {"uid": records["other"], "cid": other},
                )
                unrelated.execute(
                    text("UPDATE sasu.curricula SET title='편성 변경' WHERE curriculum_id=:id"),
                    {"id": unrelated_series},
                )
                unrelated.commit()
        finally:
            release.set()
        response = deletion.result(timeout=10)
        assert response.status_code == 200, response.text
    with Session(postgres_engine) as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM sasu.curriculum_items WHERE curriculum_id=:id"),
                {"id": related_series},
            )
            == 1
        )


def test_new_series_link_during_delete_cannot_restore_deleted_content(
    state, postgres_engine, monkeypatch
):
    client, records, path, headers, version = state
    target = records["questions"][0]["content_id"]
    series_id = create_series(postgres_engine, [])
    series_path = f"/api/curriculums/{series_id}"
    current = client.get(series_path + "?view=editor", headers=headers).json()
    deleting, release = Event(), Event()
    original = deletion_repository.delete_owned_rows

    def hold(session, content):
        files = original(session, content)
        deleting.set()
        assert release.wait(10)
        return files

    monkeypatch.setattr(deletion_repository, "delete_owned_rows", hold)
    with ThreadPoolExecutor(2) as pool:
        deletion = pool.submit(
            client.request,
            "DELETE",
            path,
            headers=headers,
            json={"expected_updated_at": version, "confirm": True},
        )
        assert deleting.wait(5)
        save = pool.submit(
            client.put,
            series_path + "/steps",
            headers=headers,
            json={
                "expected_updated_at": current["summary"]["updated_at"],
                "content_ids": [target],
            },
        )
        try:
            with pytest.raises(TimeoutError):
                save.result(timeout=0.15)
        finally:
            release.set()
        assert deletion.result(timeout=10).status_code == 200
        response = save.result(timeout=10)
        assert response.status_code == 404, response.text
        assert response.json()["detail"]["code"] == "CONTENT_NOT_FOUND"
    assert client.get(series_path + "?view=editor", headers=headers).json()["steps"] == []
