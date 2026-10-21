"""파트 3 전용 PostgreSQL 테스트 DB. 공용 fixture와 개발 DB를 변경하지 않는다."""

import os
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
from app.modules.attempts.router import router
from app.modules.questions import repository as questions_repository
from app.modules.questions.schemas import QuestionInput
from app.modules.questions.service import get_version

TEST_URL = get_settings().database_url if os.getenv("SASU_TEST_POSTGRES") == "1" else None


@pytest.fixture(scope="module")
def postgres_engine():
    if TEST_URL is None:
        pytest.skip("SASU_TEST_POSTGRES=1 필요")
    name = f"sasu_attempt_test_{uuid4().hex}"
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
            assert name.startswith("sasu_attempt_test_")
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
    # 독립 앱으로 기능 모듈의 HTTP 계약을 검증한다. 실제 앱 연결은 별도 테스트한다.
    application = FastAPI()
    register_exception_handlers(application)
    application.include_router(router, prefix="/api")

    def provide_session():
        with Session(bind=bind, join_transaction_mode="create_savepoint") as session:
            yield session

    application.dependency_overrides[get_db] = provide_session
    return TestClient(application, raise_server_exceptions=False)


@pytest.fixture
def client(database):
    with make_client(database.get_bind()) as http:
        yield http


def seed_records(session):
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
    category = session.scalar(
        text("INSERT INTO sasu.categories (name) VALUES ('분류') RETURNING category_id")
    )
    tag = session.scalar(text("INSERT INTO sasu.tags (name) VALUES ('태그') RETURNING tag_id"))
    root = get_settings().video_storage_root
    root.mkdir(parents=True, exist_ok=True)
    questions = []
    for index in range(3):
        asset = uuid4()
        relative = f"{asset.hex}.mp4"
        if index != 2:
            (root / relative).write_bytes(b"fixture video")
        session.execute(
            text("""INSERT INTO sasu.video_assets
                    (video_asset_id, storage_path, original_name,
                     mime_type, size_bytes, duration_seconds)
                    VALUES (:id, :path, :path, 'video/mp4', 13, 10)"""),
            {"id": asset, "path": relative},
        )
        content_id = session.scalar(
            text("""INSERT INTO sasu.contents
                    (created_by_user_id, video_asset_id, category_id,
                     title, core_content, source, reviewed_on)
                    VALUES (:admin, :asset, :category,
                            '영상', '핵심 내용', '검토 자료', CURRENT_DATE)
                    RETURNING content_id"""),
            {"admin": users["admin"], "asset": asset, "category": category},
        )
        session.execute(
            text("INSERT INTO sasu.content_tags VALUES (:content, :tag)"),
            {"content": content_id, "tag": tag},
        )
        if index != 1:
            session.execute(
                text(
                    "UPDATE sasu.contents SET status = 'PUBLISHED', published_at = now() "
                    "WHERE content_id = :id"
                ),
                {"id": content_id},
            )
        question_id = questions_repository.create_question(session, content_id)
        body = QuestionInput(
            question_type="OX",
            question_text="원래 문항",
            explanation="원래 해설",
            options=[
                {"option_order": 1, "option_text": "O", "is_correct": True},
                {"option_order": 2, "option_text": "X", "is_correct": False},
            ],
        )
        version = questions_repository.create_version(session, question_id, 1, body)
        questions_repository.create_options(session, version, body.options)
        questions_repository.set_current_version(session, question_id, version)
        questions.append(get_version(session, question_id, version).model_dump())
    session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    session.commit()
    return {**users, "questions": questions}


@pytest.fixture
def records(database):
    return seed_records(database)


@pytest.fixture
def committed_records(postgres_engine):
    # 경합 검증에 필요한 커밋은 이 모듈 전용 테스트 DB에만 남긴다.
    with Session(postgres_engine) as session:
        return seed_records(session)


@pytest.fixture
def http_factory():
    return make_client
