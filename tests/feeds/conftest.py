"""CNT-01용 임시 DB·영상. 개발 DB와 파트 3의 데모 데이터는 사용하지 않는다."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import PROJECT_ROOT, get_settings
from app.core.exceptions import register_exception_handlers
from app.db.session import get_db
from app.modules.feeds.router import router

TEST_URL = get_settings().database_url if os.getenv("SASU_TEST_POSTGRES") == "1" else None


@pytest.fixture(scope="module")
def postgres_engine():
    if TEST_URL is None:
        pytest.skip("SASU_TEST_POSTGRES=1 필요")
    name = f"sasu_feed_test_{uuid4().hex}"
    management = create_engine(TEST_URL, isolation_level="AUTOCOMMIT")
    engine = None
    created = False
    try:
        with management.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
            created = True
        engine = create_engine(TEST_URL.set(database=name))
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            assert name.startswith("sasu_feed_test_") and len(name) == 47
            with management.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        management.dispose()


@pytest.fixture
def database(postgres_engine):
    with postgres_engine.connect() as connection, connection.begin() as transaction:
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


def make_client(bind):
    application = FastAPI()
    register_exception_handlers(application)
    application.include_router(router, prefix="/api")

    def provide_session():
        with Session(bind=bind, join_transaction_mode="create_savepoint") as session:
            yield session

    application.dependency_overrides[get_db] = provide_session
    return TestClient(application, raise_server_exceptions=False)


@pytest.fixture
def http_factory():
    return make_client


@pytest.fixture
def client(database):
    with make_client(database.get_bind()) as http:
        yield http


def seed_users(session):
    users = {}
    prefix = uuid4().hex[:12]
    for name, role in (
        ("admin", "ADMIN"),
        ("learner", "LEARNER"),
        ("other", "LEARNER"),
        ("no_state", "LEARNER"),
    ):
        users[name] = session.scalar(
            text("""INSERT INTO sasu.app_users (username, display_name, role)
                    VALUES (:name, :name, :role) RETURNING user_id"""),
            {"name": f"{prefix}_{name}", "role": role},
        )
        if name in {"learner", "other"}:
            session.execute(
                text("INSERT INTO sasu.user_settings (user_id) VALUES (:id)"), {"id": users[name]}
            )
    for table in ("categories", "tags"):
        column = "category_id" if table == "categories" else "tag_id"
        users[column] = session.scalar(
            text(f"INSERT INTO sasu.{table} (name) VALUES (:name) RETURNING {column}"),
            {"name": prefix},
        )
    session.commit()
    return users


@pytest.fixture
def records(database):
    return seed_users(database)


@pytest.fixture
def content_factory(database, records):
    def create(
        *,
        status="PUBLISHED",
        media="available",
        mime_type="video/mp4",
        category_id=None,
        tag_ids=None,
        published_at=None,
    ):
        asset = uuid4()
        path = f"{asset.hex}.mp4"
        root = get_settings().video_storage_root
        root.mkdir(parents=True, exist_ok=True)
        if media != "missing":
            (root / path).write_bytes(b"fixture" if media == "available" else b"bad")
        database.execute(
            text("""INSERT INTO sasu.video_assets
                    (video_asset_id, storage_path, original_name, mime_type,
                     size_bytes, duration_seconds)
                    VALUES (:id, :path, :path, :mime, 7, 10)"""),
            {"id": asset, "path": path, "mime": mime_type},
        )
        content_id = database.scalar(
            text("""INSERT INTO sasu.contents
                    (created_by_user_id, video_asset_id, category_id, title,
                     core_content, source, reviewed_on, status, published_at)
                    VALUES (:admin, :asset, :category, '피드 영상', '핵심 내용',
                            '검토 자료', CURRENT_DATE, :status, :published)
                    RETURNING content_id"""),
            {
                "admin": records["admin"],
                "asset": asset,
                "category": category_id or records["category_id"],
                "status": status,
                "published": published_at or datetime.now(UTC),
            },
        )
        for tag in tag_ids if tag_ids is not None else [records["tag_id"]]:
            database.execute(
                text("INSERT INTO sasu.content_tags VALUES (:content, :tag)"),
                {"content": content_id, "tag": tag},
            )
        database.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        database.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        database.commit()
        return content_id

    return create
