"""파트 3의 격리 DB fixture를 재사용하고 복습용 기록을 준비한다."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.db.session import get_db
from app.modules.attempts.router import router as attempts_router
from app.modules.questions import repository as questions_repository
from app.modules.questions.schemas import QuestionInput
from app.modules.questions.service import get_version
from app.modules.responses.router import router as responses_router
from app.modules.reviews.router import router as reviews_router
from tests.attempts.conftest import committed_records as committed_records
from tests.attempts.conftest import database as database
from tests.attempts.conftest import postgres_engine as postgres_engine
from tests.attempts.conftest import records as records


def make_client(bind):
    application = FastAPI()
    register_exception_handlers(application)
    for router in (reviews_router, attempts_router, responses_router):
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


@pytest.fixture
def http_factory():
    return make_client


@pytest.fixture
def question_factory(database, records):
    def create(*, category=None, published=True, media=True, with_quiz=True, published_at=None):
        if category is None:
            category = database.scalar(
                text("SELECT category_id FROM sasu.contents WHERE content_id = :id"),
                {"id": records["questions"][0]["content_id"]},
            )
        asset = uuid4()
        relative = f"{asset.hex}.mp4"
        if media:
            (get_settings().video_storage_root / relative).write_bytes(b"fixture video")
        database.execute(
            text("""INSERT INTO sasu.video_assets
                    (video_asset_id, storage_path, original_name,
                     mime_type, size_bytes, duration_seconds)
                    VALUES (:id, :path, :path, 'video/mp4', 13, 10)"""),
            {"id": asset, "path": relative},
        )
        content = database.scalar(
            text("""INSERT INTO sasu.contents
                    (created_by_user_id, video_asset_id, category_id, title,
                     core_content, source, reviewed_on)
                    VALUES (:admin, :asset, :category, '추가 콘텐츠', '핵심', '출처', CURRENT_DATE)
                    RETURNING content_id"""),
            {"admin": records["admin"], "asset": asset, "category": category},
        )
        database.execute(
            text("""INSERT INTO sasu.content_tags (content_id, tag_id)
                    SELECT :content, tag_id FROM sasu.content_tags WHERE content_id = :original"""),
            {"content": content, "original": records["questions"][0]["content_id"]},
        )
        if published:
            database.execute(
                text(
                    "UPDATE sasu.contents SET status = 'PUBLISHED', published_at = :at "
                    "WHERE content_id = :id"
                ),
                {"id": content, "at": published_at or datetime(2026, 10, 20, tzinfo=UTC)},
            )
        result = {"content_id": content}
        if with_quiz:
            question_id = questions_repository.create_question(database, content)
            body = QuestionInput(
                question_type="OX",
                question_text="추가 문항",
                explanation="추가 해설",
                options=[
                    {"option_order": 1, "option_text": "O", "is_correct": True},
                    {"option_order": 2, "option_text": "X", "is_correct": False},
                ],
            )
            version = questions_repository.create_version(database, question_id, 1, body)
            questions_repository.create_options(database, version, body.options)
            questions_repository.set_current_version(database, question_id, version)
            result = get_version(database, question_id, version).model_dump()
        database.commit()
        return result

    return create


@pytest.fixture
def watch(database, records):
    def record(question=None, *, user="learner", completed=True, at=None):
        question = question or records["questions"][0]
        database.execute(
            text("""INSERT INTO sasu.watch_records
                    (user_id, learning_epoch, content_id, first_played_at, last_watched_at,
                     view_counted_at, completed_at, max_coverage_ratio)
                    VALUES (:user, 1, :content, :at, :at, :at, :completed, :coverage)"""),
            {
                "user": records[user],
                "content": question["content_id"],
                "at": at or datetime(2026, 10, 20, tzinfo=UTC),
                "completed": (at or datetime(2026, 10, 20, tzinfo=UTC)) if completed else None,
                "coverage": 0.9 if completed else 0.5,
            },
        )
        database.commit()

    return record


@pytest.fixture
def respond(database, records):
    def record(question=None, *, user="learner", context="VIDEO_END", result="WRONG", at=None):
        question = question or records["questions"][0]
        attempt = uuid4()
        database.execute(
            text("""INSERT INTO sasu.quiz_attempts
                    (attempt_id, user_id, learning_epoch, quiz_id, quiz_version_id, context)
                    VALUES (:id, :user, 1, :question, :version, :context)"""),
            {
                "id": attempt,
                "user": records[user],
                "question": question["question_id"],
                "version": question["question_version_id"],
                "context": context,
            },
        )
        response_id = database.scalar(
            text("""INSERT INTO sasu.quiz_responses
                    (attempt_id, quiz_version_id, selected_option_id, result, submitted_at)
                    VALUES (:attempt, :version, :option, :result, :at) RETURNING response_id"""),
            {
                "attempt": attempt,
                "version": question["question_version_id"],
                "option": None
                if result == "SKIPPED"
                else next(
                    option["option_id"]
                    for option in question["options"]
                    if option["is_correct"] == (result == "CORRECT")
                ),
                "result": result,
                "at": at or datetime(2026, 10, 20, tzinfo=UTC),
            },
        )
        database.commit()
        return response_id

    return record
