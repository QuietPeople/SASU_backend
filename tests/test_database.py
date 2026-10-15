"""요청 세션의 종료와 서비스에서 결정하는 커밋 경계를 검증한다."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db import session as db_session


@pytest.fixture
def database(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE sample (id INTEGER PRIMARY KEY)"))
    factory = sessionmaker(bind=engine)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(db_session, "get_session_factory", lambda: factory)
            yield engine
    finally:
        engine.dispose()


def count_records(engine):
    with engine.connect() as connection:
        return connection.scalar(text("SELECT count(*) FROM sample"))


def test_uncommitted_work_is_rolled_back_when_request_ends(database):
    dependency = db_session.get_db()
    session = next(dependency)
    session.execute(text("INSERT INTO sample VALUES (1)"))
    dependency.close()
    assert count_records(database) == 0


def test_service_transaction_is_committed(database):
    dependency = db_session.get_db()
    session = next(dependency)
    with session.begin():
        session.execute(text("INSERT INTO sample VALUES (1)"))
    dependency.close()
    assert count_records(database) == 1


def test_request_failure_does_not_leave_partial_writes(database):
    dependency = db_session.get_db()
    session = next(dependency)
    session.execute(text("INSERT INTO sample VALUES (1)"))
    with pytest.raises(ValueError, match="request failed"):
        dependency.throw(ValueError("request failed"))
    assert count_records(database) == 0
