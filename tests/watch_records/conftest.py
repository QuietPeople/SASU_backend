"""시청 기록 API PostgreSQL 검증 환경."""

import os
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import PROJECT_ROOT, get_settings
from app.db.session import get_db
from app.main import app

TEST_URL = get_settings().database_url if os.getenv("SASU_TEST_POSTGRES") == "1" else None


@pytest.fixture(scope="module")
def postgres_engine():
    if TEST_URL is None:
        pytest.skip("SASU_TEST_POSTGRES=1 필요")
    database_name = f"sasu_watch_test_{uuid4().hex}"
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
            assert database_name.startswith("sasu_watch_test_")
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


@pytest.fixture
def seed(database):
    """학습자 user1, 관리자 admin, user_settings(학습자만)."""
    database.execute(
        text(
            "INSERT INTO sasu.app_users (username, display_name, role)"
            " VALUES ('user1', '학습자', 'LEARNER'), ('admin', '관리자', 'ADMIN')"
        )
    )
    database.flush()
    learner_id = database.scalar(
        text("SELECT user_id FROM sasu.app_users WHERE username = 'user1'")
    )
    admin_id = database.scalar(
        text("SELECT user_id FROM sasu.app_users WHERE username = 'admin'")
    )
    database.execute(
        text("INSERT INTO sasu.user_settings (user_id) VALUES (:uid)"),
        {"uid": learner_id},
    )
    database.flush()
    return {"learner_id": learner_id, "admin_id": admin_id}


@pytest.fixture
def published_content(database, seed):
    """공개 콘텐츠 1개(영상 자산 포함) 삽입 후 (content_id, asset_id, duration) 반환."""
    admin_id = seed["admin_id"]
    asset_id = str(uuid4())
    duration = 60.0

    cat_id = database.scalar(
        text("INSERT INTO sasu.categories (name) VALUES ('테스트') RETURNING category_id")
    )
    tag_id = database.scalar(
        text("INSERT INTO sasu.tags (name) VALUES ('태그') RETURNING tag_id")
    )
    database.execute(
        text(
            "INSERT INTO sasu.video_assets"
            " (video_asset_id, storage_path, original_name, mime_type, size_bytes, duration_seconds)"
            " VALUES (:aid, 'videos/test.mp4', 'test.mp4', 'video/mp4', 1048576, :dur)"
        ),
        {"aid": asset_id, "dur": duration},
    )
    content_id = database.scalar(
        text(
            "INSERT INTO sasu.contents"
            " (created_by_user_id, video_asset_id, category_id, title, core_content,"
            "  source, reviewed_on, status, published_at)"
            " VALUES (:uid, :aid, :cat, '테스트', '핵심',"
            "         '출처', CURRENT_DATE, 'PUBLISHED', now())"
            " RETURNING content_id"
        ),
        {"uid": admin_id, "aid": asset_id, "cat": cat_id},
    )
    database.execute(
        text("INSERT INTO sasu.content_tags (content_id, tag_id) VALUES (:cid, :tid)"),
        {"cid": content_id, "tid": tag_id},
    )
    database.flush()
    return {"content_id": content_id, "asset_id": asset_id, "duration": duration}
