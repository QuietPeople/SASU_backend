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


def list_response_rows(session: Session, ids: list[int], actor: Actor):
    return session.execute(
        text("""
        SELECT r.response_id, r.attempt_id, a.user_id, a.context, r.result,
               r.selected_option_id, r.submitted_at, w.status AS wrong_status,
               w.wrong_count, w.resolved_at, q.quiz_id AS question_id, q.content_id,
               v.quiz_version_id AS question_version_id, v.question_text, v.explanation,
               v.version_no, v.created_at, q.current_version_id=v.quiz_version_id AS is_current,
               CASE v.question_type WHEN 'MCQ3' THEN 'MCQ_3' WHEN 'MCQ4' THEN 'MCQ_4'
                    ELSE 'OX' END AS question_type,
               (SELECT jsonb_agg(jsonb_build_object('option_id', o.option_id,
                 'option_order', o.position, 'option_text', o.option_text,
                 'is_correct', o.is_correct) ORDER BY o.position) FROM sasu.quiz_options o
                 WHERE o.quiz_version_id=v.quiz_version_id) AS options
        FROM unnest(CAST(:ids AS bigint[])) WITH ORDINALITY wanted(id, ord)
        JOIN sasu.quiz_responses r ON r.response_id=wanted.id
        JOIN sasu.quiz_attempts a USING(attempt_id)
        JOIN sasu.quiz_versions v ON v.quiz_version_id=r.quiz_version_id
        JOIN sasu.quizzes q ON q.quiz_id=v.quiz_id
        LEFT JOIN sasu.wrong_answers w ON w.user_id=a.user_id
            AND w.quiz_version_id=v.quiz_version_id
        WHERE a.user_id=:actor OR :admin ORDER BY wanted.ord
    """),
        {"ids": ids, "actor": actor.user_id, "admin": actor.role == "ADMIN"},
    ).mappings()
