from sqlalchemy import delete, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.likes.tables import content_likes


def lock_learner_state(session: Session, user_id: int) -> int | None:
    return session.scalar(
        text(
            """
            SELECT settings.learning_epoch
            FROM sasu.user_settings settings
            JOIN sasu.app_users users ON users.user_id = settings.user_id
            WHERE settings.user_id = :user_id AND users.role = 'LEARNER'
            FOR UPDATE OF settings
            """
        ),
        {"user_id": user_id},
    )


def lock_content_status(session: Session, content_id: int) -> str | None:
    return session.scalar(
        text("SELECT status FROM sasu.contents WHERE content_id = :content_id FOR UPDATE"),
        {"content_id": content_id},
    )


def insert_like(session: Session, user_id: int, content_id: int, learning_epoch: int) -> None:
    session.execute(
        insert(content_likes)
        .values(user_id=user_id, content_id=content_id, learning_epoch=learning_epoch)
        .on_conflict_do_nothing(
            index_elements=[content_likes.c.user_id, content_likes.c.content_id]
        )
    )


def delete_like(session: Session, user_id: int, content_id: int) -> None:
    session.execute(
        delete(content_likes).where(
            content_likes.c.user_id == user_id, content_likes.c.content_id == content_id
        )
    )


def get_like_count(session: Session, content_id: int) -> int:
    return session.execute(
        text("SELECT like_count FROM sasu.content_metrics WHERE content_id = :content_id"),
        {"content_id": content_id},
    ).scalar_one()
