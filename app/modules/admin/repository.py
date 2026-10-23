"""적재된 sasu 테이블·뷰·함수에 접근한다. 다른 모듈의 ORM 모델을 중복 선언하지 않는다."""

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.modules.statistics.tables import content_metrics
from app.modules.watch_records.tables import watch_records


def find_reaction_stats(session: Session, content_id: int):
    played = (
        select(func.count())
        .select_from(watch_records)
        .where(watch_records.c.content_id == content_id)
    )
    return (
        session.execute(
            select(
                content_metrics.c.view_count,
                content_metrics.c.like_count,
                content_metrics.c.saved_count,
                played.scalar_subquery().label("played_count"),
                played.where(watch_records.c.completed_at.is_not(None))
                .scalar_subquery()
                .label("completed_count"),
            ).where(content_metrics.c.content_id == content_id)
        )
        .mappings()
        .one_or_none()
    )


def count_learning_records(session: Session, user_id: int):
    return (
        session.execute(
            text(
                """
            SELECT
                (SELECT count(*) FROM sasu.watch_visits
                 WHERE user_id = :user_id) AS watch_visits,
                (SELECT count(*) FROM sasu.watch_records
                 WHERE user_id = :user_id) AS watch_records,
                (SELECT count(*) FROM sasu.content_likes
                 WHERE user_id = :user_id) AS likes,
                (SELECT count(*) FROM sasu.saved_contents
                 WHERE user_id = :user_id) AS saved_contents,
                (SELECT count(*) FROM sasu.quiz_responses responses
                 JOIN sasu.quiz_attempts attempts USING (attempt_id)
                 WHERE attempts.user_id = :user_id) AS responses,
                (SELECT count(*) FROM sasu.quiz_attempts
                 WHERE user_id = :user_id) AS attempts,
                (SELECT count(*) FROM sasu.wrong_answers
                 WHERE user_id = :user_id) AS wrong_answers,
                (SELECT count(*) FROM sasu.learning_events
                 WHERE user_id = :user_id) AS events
            """
            ),
            {"user_id": user_id},
        )
        .mappings()
        .one()
    )


def reset_learning(session: Session, user_id: int, expected_epoch: int) -> int:
    return session.scalar(
        text("SELECT sasu.reset_learning(:user_id, :expected_epoch)"),
        {"user_id": user_id, "expected_epoch": expected_epoch},
    )
