"""테스트 DB를 별도로 만들며 개발 DB에 자료를 삽입하지 않는다."""

import os
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from alembic import command
from app.api.router import api_router
from app.core.config import PROJECT_ROOT, get_settings
from app.core.exceptions import register_exception_handlers
from app.db.session import get_db
from app.modules.dashboard.router import router as dashboard_router
from app.modules.statistics.router import router as statistics_router

TEST_URL = get_settings().database_url if os.getenv("SASU_TEST_POSTGRES") == "1" else None


@pytest.fixture(scope="module")
def postgres_engine():
    isolated = os.getenv("SASU_PART4_PGLITE_URL")
    if isolated:
        engine = create_engine(isolated, poolclass=NullPool)
        try:
            with engine.begin() as c:
                if c.scalar(text("SELECT to_regnamespace('sasu')")) is not None:
                    raise RuntimeError("PGlite 검증은 빈 임시 DB에서만 실행합니다.")
                config = Config(str(PROJECT_ROOT / "alembic.ini"))
                config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
                config.attributes["connection"] = c
                command.upgrade(config, "head")
            yield engine
        finally:
            engine.dispose()
        return
    if TEST_URL is None:
        pytest.skip("SASU_TEST_POSTGRES=1과 별도 테스트 서버 접속 설정 필요")
    database_name = f"sasu_part4_test_{uuid4().hex}"
    management = create_engine(TEST_URL, isolation_level="AUTOCOMMIT")
    engine = None
    created = False
    try:
        with management.connect() as c:
            c.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
            created = True
        engine = create_engine(TEST_URL.set(database=database_name))
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        with engine.begin() as c:
            config.attributes["connection"] = c
            command.upgrade(config, "head")
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with management.connect() as c:
                c.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')
        management.dispose()


@pytest.fixture
def database(postgres_engine):
    with postgres_engine.connect() as c, c.begin() as transaction:
        with Session(bind=c, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


@pytest.fixture
def client(database):
    # 파트1 소유 router.py를 편집하지 않고 최종 연결 상태를 재현한다.
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(api_router)
    app.include_router(dashboard_router, prefix="/api")
    app.include_router(statistics_router, prefix="/api")

    def session_override():
        yield database

    app.dependency_overrides[get_db] = session_override
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
