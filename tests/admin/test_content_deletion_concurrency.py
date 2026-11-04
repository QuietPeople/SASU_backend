"""서로 다른 연결의 실제 잠금이 삭제와 충돌할 때 원자적으로 재시도하는지 검증한다."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.contents.deletion_service import delete_content
from app.modules.contents.schemas import ContentDelete
from app.modules.questions.schemas import QuestionInput
from app.modules.questions.service import register_question


@pytest.fixture
def owned_content(postgres_engine):
    with postgres_engine.begin() as connection:
        users = [
            connection.scalar(
                text("""
            INSERT INTO sasu.app_users (username, display_name, role)
            VALUES (:name, '잠금 테스트', :role) RETURNING user_id
        """),
                {"name": uuid4().hex, "role": role},
            )
            for role in ("ADMIN", "LEARNER")
        ]
        connection.execute(
            text("INSERT INTO sasu.user_settings (user_id) VALUES (:id)"), {"id": users[1]}
        )
        content = connection.scalar(
            text("""
            INSERT INTO sasu.contents (created_by_user_id) VALUES (:id) RETURNING content_id
        """),
            {"id": users[0]},
        )
        connection.execute(
            text("""
            INSERT INTO sasu.content_likes (user_id, learning_epoch, content_id)
            VALUES (:user, 1, :content)
        """),
            {"user": users[1], "content": content},
        )
        curriculum = connection.scalar(
            text("""
            INSERT INTO sasu.curricula (title) VALUES ('삭제 잠금 시리즈') RETURNING curriculum_id
        """)
        )
        connection.execute(
            text("INSERT INTO sasu.curriculum_items VALUES (:id, :content, 1)"),
            {"id": curriculum, "content": content},
        )
    with Session(postgres_engine) as session:
        version = register_question(
            session,
            content,
            QuestionInput.model_validate(
                {
                    "question_type": "OX",
                    "question_text": "문제",
                    "explanation": "해설",
                    "options": [
                        {"option_order": 1, "option_text": "O", "is_correct": True},
                        {"option_order": 2, "option_text": "X", "is_correct": False},
                    ],
                }
            ),
        )
    return {
        "contents": content,
        "admin": users[0],
        "user_settings": users[1],
        "curricula": curriculum,
        "quizzes": version.question_id,
    }


@pytest.mark.parametrize(
    "table,key",
    [
        ("contents", "content_id"),
        ("user_settings", "user_id"),
        ("curricula", "curriculum_id"),
        ("quizzes", "quiz_id"),
    ],
)
def test_busy_dependency_returns_conflict_and_delete_can_retry(
    postgres_engine, owned_content, table, key
):
    target = owned_content["contents"]
    with Session(postgres_engine) as busy, Session(postgres_engine) as deleting:
        busy.execute(
            text(f"SELECT {key} FROM sasu.{table} WHERE {key}=:id FOR UPDATE"),
            {"id": owned_content[table]},
        ).all()
        with pytest.raises(ApiError) as conflict:
            delete_content(deleting, owned_content["admin"], target, ContentDelete(confirm=True))
        assert conflict.value.status_code == 409
        assert conflict.value.code == "CONTENT_IN_USE"
        assert not deleting.in_transaction()
        assert (
            busy.scalar(
                text("SELECT count(*) FROM sasu.contents WHERE content_id=:id"), {"id": target}
            )
            == 1
        )
        busy.rollback()
        delete_content(deleting, owned_content["admin"], target, ContentDelete(confirm=True))
        assert (
            deleting.scalar(
                text("SELECT count(*) FROM sasu.contents WHERE content_id=:id"), {"id": target}
            )
            == 0
        )
