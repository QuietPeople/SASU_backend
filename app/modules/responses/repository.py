"""소유권을 확인한 응답과 제출 버전의 현재 오답 상태 조회."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import Actor


def find_response(session: Session, response_id: int, actor: Actor):
    return (
        session.execute(
            text(
                """
                SELECT r.response_id, r.attempt_id, a.user_id, a.quiz_id AS question_id,
                       r.quiz_version_id AS question_version_id, a.context, r.result,
                       r.selected_option_id, r.submitted_at, w.status AS wrong_status,
                       w.wrong_count, w.resolved_at
                FROM sasu.quiz_responses r
                JOIN sasu.quiz_attempts a ON a.attempt_id = r.attempt_id
                LEFT JOIN sasu.wrong_answers w
                  ON w.user_id = a.user_id AND w.quiz_version_id = r.quiz_version_id
                WHERE r.response_id = :id AND (a.user_id = :actor_id OR :is_admin)
                """
            ),
            {"id": response_id, "actor_id": actor.user_id, "is_admin": actor.role == "ADMIN"},
        )
        .mappings()
        .one_or_none()
    )
