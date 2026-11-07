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
from app.modules.contents import lifecycle_repository
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
    original = lifecycle_repository.lock_deletion

    def lock(session):
        started.set()
        original(session)

    monkeypatch.setattr(lifecycle_repository, "lock_deletion", lock)
    with Session(postgres_engine) as learner, ThreadPoolExecutor(1) as pool:
        learner.execute(
            text("SELECT user_id FROM sasu.user_settings WHERE user_id=:id FOR UPDATE"),
            {"id": records["learner"]},
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
        finally:
            learner.commit()
        response = deletion.result(timeout=10)
        assert response.status_code == 200, response.text


def test_learning_request_after_delete_cannot_recreate_orphan_records(state, monkeypatch):
    client, records, path, headers, version = state
    deleted, release = Event(), Event()
    original = lifecycle_repository.delete_owned_rows

    def hold(session, content):
        files = original(session, content)
        deleted.set()
        assert release.wait(10)
        return files

    monkeypatch.setattr(lifecycle_repository, "delete_owned_rows", hold)
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
