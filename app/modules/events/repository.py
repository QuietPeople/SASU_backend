import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def lock_settings(session: Session, user_id: int) -> int | None:
    return session.scalar(
        text("SELECT learning_epoch FROM sasu.user_settings WHERE user_id = :uid FOR UPDATE"),
        {"uid": user_id},
    )


def get_content_status(session: Session, content_id: int) -> str | None:
    return session.scalar(
        text("SELECT status FROM sasu.contents WHERE content_id = :cid"),
        {"cid": content_id},
    )


def insert_event(
    session: Session,
    *,
    event_id: UUID,
    user_id: int,
    learning_epoch: int,
    event_type: str,
    content_id: int | None,
    quiz_version_id: int | None,
    attempt_id: UUID | None,
    metadata: dict,
) -> bool:
    """Insert a learning event. Returns True if inserted, False if duplicate."""
    result = session.execute(
        text(
            """
            INSERT INTO sasu.learning_events
              (event_id, user_id, learning_epoch, event_type,
               content_id, quiz_version_id, attempt_id, metadata)
            VALUES
              (:eid, :uid, :epoch, :etype,
               :cid, :vid, CAST(:aid AS uuid), CAST(:meta AS jsonb))
            ON CONFLICT (event_id) DO NOTHING
            RETURNING event_id
            """
        ),
        {
            "eid": str(event_id),
            "uid": user_id,
            "epoch": learning_epoch,
            "etype": event_type,
            "cid": content_id,
            "vid": quiz_version_id,
            "aid": str(attempt_id) if attempt_id is not None else None,
            "meta": json.dumps(metadata),
        },
    )
    return result.one_or_none() is not None
