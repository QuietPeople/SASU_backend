from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def lock_event_id(session: Session, event_id: UUID) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"event:{event_id}"},
    )


def find_event(session: Session, event_id: UUID):
    return (
        session.execute(
            text("""SELECT e.* FROM sasu.learning_events e
            WHERE e.event_id = :id
               OR COALESCE(e.metadata->'client_event_ids', '[]'::jsonb) ? :client_id
            FOR UPDATE OF e"""),
            {"id": event_id, "client_id": str(event_id)},
        )
        .mappings()
        .one_or_none()
    )


def find_display(session: Session, attempt_id: UUID):
    return (
        session.execute(
            text("""SELECT * FROM sasu.learning_events
            WHERE attempt_id = :id AND event_type = 'QUIZ_DISPLAYED' FOR UPDATE"""),
            {"id": attempt_id},
        )
        .mappings()
        .one_or_none()
    )


def remember_retry_id(session: Session, event_id: UUID, client_event_id: UUID) -> None:
    # 같은 풀이의 다른 재전송 키도 예약한다. 사용자 metadata나 검색어는 저장하지 않는다.
    session.execute(
        text("""UPDATE sasu.learning_events SET metadata = jsonb_set(
            metadata, '{client_event_ids}',
            COALESCE(metadata->'client_event_ids', '[]'::jsonb)
            || jsonb_build_array(CAST(:key AS text))
        ) WHERE event_id = :id"""),
        {"id": event_id, "key": str(client_event_id)},
    )


def get_attempt(session: Session, attempt_id: UUID):
    return (
        session.execute(
            text("""SELECT a.*, q.content_id FROM sasu.quiz_attempts a
            JOIN sasu.quizzes q USING (quiz_id)
            WHERE a.attempt_id = :id FOR UPDATE OF a"""),
            {"id": attempt_id},
        )
        .mappings()
        .one_or_none()
    )


def get_version_content(session: Session, version_id: int):
    return session.scalar(
        text("""SELECT q.content_id FROM sasu.quiz_versions v
            JOIN sasu.quizzes q USING (quiz_id) WHERE v.quiz_version_id = :id"""),
        {"id": version_id},
    )


def get_content_status(session: Session, content_id: int) -> str | None:
    return session.scalar(
        text("SELECT status FROM sasu.contents WHERE content_id = :id FOR KEY SHARE"),
        {"id": content_id},
    )


def insert_event(
    session, *, event_id, user_id, epoch, event_type, content_id, version_id, attempt_id
):
    return (
        session.execute(
            text("""INSERT INTO sasu.learning_events
            (event_id, user_id, learning_epoch, event_type, content_id, quiz_version_id, attempt_id)
            VALUES (:id, :user, :epoch, :type, :content, :version, :attempt)
            RETURNING *"""),
            {
                "id": event_id,
                "user": user_id,
                "epoch": epoch,
                "type": event_type,
                "content": content_id,
                "version": version_id,
                "attempt": attempt_id,
            },
        )
        .mappings()
        .one()
    )
