"""개발 데이터를 보존하는 관리자·공통 분류 API의 PostgreSQL 검증 환경."""

import os
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import PROJECT_ROOT, get_settings
from app.db.session import get_db
from app.main import app

# 공통 autouse 설정 격리 전, 명시적으로 허용한 테스트 서버 연결만 보관한다.
TEST_URL = get_settings().database_url if os.getenv("SASU_TEST_POSTGRES") == "1" else None


@pytest.fixture(scope="module")
def postgres_engine():
    if TEST_URL is None:
        pytest.skip("SASU_TEST_POSTGRES=1 필요")
    database_name = f"sasu_admin_test_{uuid4().hex}"
    management_engine = create_engine(TEST_URL, isolation_level="AUTOCOMMIT")
    test_engine = None
    created = False
    try:
        with management_engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
            created = True
        test_engine = create_engine(TEST_URL.set(database=database_name))
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield test_engine
    finally:
        if test_engine is not None:
            test_engine.dispose()
        if created:
            # 직접 생성에 성공한 UUID 이름의 테스트 DB만 정리한다.
            assert database_name.startswith("sasu_admin_test_")
            with management_engine.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')
        management_engine.dispose()


@pytest.fixture
def database(postgres_engine):
    with postgres_engine.connect() as connection, connection.begin() as transaction:
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


@pytest.fixture
def client(database):
    def session_override():
        yield database

    app.dependency_overrides[get_db] = session_override
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def skip_application_startup_check(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "check_database_connection", lambda: None)
    monkeypatch.setattr(main, "close_database", lambda: None)
