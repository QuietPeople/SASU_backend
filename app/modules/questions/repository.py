"""기존 문항·불변 버전·보기 테이블 접근. 버전과 보기를 UPDATE하지 않는다."""

from sqlalchemy import text
from sqlalchemy.orm import Session


def find_content(session: Session, content_id: int, lock: bool = False):
    statement = "SELECT content_id, status FROM sasu.contents WHERE content_id = :id"
    if lock:
        statement += " FOR UPDATE"
    return session.execute(text(statement), {"id": content_id}).mappings().one_or_none()


def find_question(session: Session, question_id: int, lock: bool = False):
    statement = (
        "SELECT quiz_id, content_id, current_version_id FROM sasu.quizzes WHERE quiz_id = :id"
    )
    if lock:
        statement += " FOR UPDATE"
    return session.execute(text(statement), {"id": question_id}).mappings().one_or_none()


def question_for_content(session: Session, content_id: int):
    return (
        session.execute(
            text("SELECT quiz_id, current_version_id FROM sasu.quizzes WHERE content_id = :id"),
            {"id": content_id},
        )
        .mappings()
        .one_or_none()
    )


def version_header(session: Session, question_id: int, version_id: int):
    return (
        session.execute(
            text(
                """
            SELECT q.quiz_id AS question_id, v.quiz_version_id AS question_version_id,
                   q.content_id, v.version_no, v.question_type, v.question_text, v.explanation,
                   v.created_at, (q.current_version_id = v.quiz_version_id) AS is_current
            FROM sasu.quiz_versions v JOIN sasu.quizzes q USING (quiz_id)
            WHERE q.quiz_id = :question AND v.quiz_version_id = :version
            """
            ),
            {"question": question_id, "version": version_id},
        )
        .mappings()
        .one_or_none()
    )


def version_options(session: Session, version_id: int):
    return (
        session.execute(
            text(
                """SELECT option_id, position AS option_order, option_text, is_correct
               FROM sasu.quiz_options WHERE quiz_version_id = :id ORDER BY position"""
            ),
            {"id": version_id},
        )
        .mappings()
        .all()
    )


def create_question(session: Session, content_id: int) -> int:
    return session.scalar(
        text("INSERT INTO sasu.quizzes (content_id) VALUES (:id) RETURNING quiz_id"),
        {"id": content_id},
    )


def create_version(session: Session, question_id: int, version_no: int, request) -> int:
    return session.scalar(
        text(
            """INSERT INTO sasu.quiz_versions
               (quiz_id, version_no, question_type, question_text, explanation)
               VALUES (:question, :number, :type, :text, :explanation) RETURNING quiz_version_id"""
        ),
        {
            "question": question_id,
            "number": version_no,
            "type": request.question_type.replace("_", ""),
            "text": request.question_text,
            "explanation": request.explanation,
        },
    )


def create_options(session: Session, version_id: int, options) -> None:
    session.execute(
        text(
            """INSERT INTO sasu.quiz_options
               (quiz_version_id, position, option_text, is_correct)
               VALUES (:version, :position, :text, :correct)"""
        ),
        [
            {
                "version": version_id,
                "position": option.option_order,
                "text": option.option_text,
                "correct": option.is_correct,
            }
            for option in options
        ],
    )


def set_current_version(session: Session, question_id: int, version_id: int) -> None:
    session.execute(
        text("UPDATE sasu.quizzes SET current_version_id = :version WHERE quiz_id = :question"),
        {"question": question_id, "version": version_id},
    )


def list_versions(session: Session, question_id: int, page: int, size: int):
    total = session.scalar(
        text("SELECT count(*) FROM sasu.quiz_versions WHERE quiz_id = :id"), {"id": question_id}
    )
    offset = (page - 1) * size
    if offset >= total:
        return [], total
    rows = (
        session.execute(
            text(
                """
            SELECT q.quiz_id AS question_id, v.quiz_version_id AS question_version_id, v.version_no,
                   (v.quiz_version_id = q.current_version_id) AS is_current, v.created_at,
                   (SELECT count(*) FROM sasu.quiz_responses r
                    WHERE r.quiz_version_id = v.quiz_version_id) AS response_count
            FROM sasu.quiz_versions v JOIN sasu.quizzes q USING (quiz_id)
            WHERE q.quiz_id = :id ORDER BY v.version_no DESC LIMIT :size OFFSET :offset
            """
            ),
            {"id": question_id, "size": size, "offset": offset},
        )
        .mappings()
        .all()
    )
    return rows, total
