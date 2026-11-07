"""새 이력까지 적용한 임시 PostgreSQL DB에서 실제 앱의 콘텐츠 제어를 검증한다."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import main
from app.db.session import get_db
from tests.attempts.conftest import database as database
from tests.attempts.conftest import postgres_engine as postgres_engine
from tests.attempts.conftest import seed_records


@pytest.fixture
def context(database, monkeypatch):
    records = seed_records(database)
    monkeypatch.setattr(main, "check_database_connection", lambda: None)

    def provide_session():
        with Session(bind=database.get_bind(), join_transaction_mode="create_savepoint") as session:
            yield session

    monkeypatch.setitem(main.app.dependency_overrides, get_db, provide_session)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        yield SimpleNamespace(
            client=client,
            database=database,
            records=records,
            content_id=records["questions"][0]["content_id"],
            headers={"X-Actor-Id": str(records["admin"])},
            learner={"X-Actor-Id": str(records["learner"]), "X-Record-Generation": "0"},
        )
