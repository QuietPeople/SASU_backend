"""기존 풀이·학습 상태 조회. 잠금 순서는 사용자 상태 → 풀이 ID → 콘텐츠 → 문항."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def learner_epoch(session: Session, user_id: int, *, write: bool) -> int | None:
    lock = "UPDATE" if write else "SHARE"
    return session.scalar(
        text(
            "SELECT s.learning_epoch FROM sasu.user_settings s "
            "JOIN sasu.app_users u ON u.user_id = s.user_id "
            f"WHERE s.user_id = :id AND u.role = 'LEARNER' FOR {lock} OF s"
        ),
        {"id": user_id},
    )


def lock_attempt_id(session: Session, attempt_id: UUID) -> None:
    # 아직 행이 없는 같은 UUID의 동시 생성을 다른 사용자 사이에서도 직렬화한다.
    # PK는 최종 무결성을 보장하고, 이 잠금은 충돌을 업무 오류로 반환하기 위한 것이다.
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:id AS text), 0))"),
        {"id": attempt_id},
    )


def find_attempt(session: Session, attempt_id: UUID):
    return (
        session.execute(
            text(
                """SELECT a.attempt_id, a.user_id, a.learning_epoch, a.quiz_id,
                          a.quiz_version_id, a.context, a.created_at, r.response_id
                   FROM sasu.quiz_attempts a
                   LEFT JOIN sasu.quiz_responses r ON r.attempt_id = a.attempt_id
                   WHERE a.attempt_id = :id"""
            ),
            {"id": attempt_id},
        )
        .mappings()
        .one_or_none()
    )


def question_content_id(session: Session, question_id: int) -> int | None:
    return session.scalar(
        text("SELECT content_id FROM sasu.quizzes WHERE quiz_id = :id"), {"id": question_id}
    )


def lock_content(session: Session, content_id: int):
    return (
        session.execute(
            text(
                """SELECT c.status, v.storage_path FROM sasu.contents c
                   LEFT JOIN sasu.video_assets v USING (video_asset_id)
                   WHERE c.content_id = :id FOR SHARE OF c"""
            ),
            {"id": content_id},
        )
        .mappings()
        .one_or_none()
    )


def lock_question(session: Session, question_id: int):
    return (
        session.execute(
            text(
                """SELECT quiz_id, content_id, current_version_id
                   FROM sasu.quizzes WHERE quiz_id = :id FOR SHARE"""
            ),
            {"id": question_id},
        )
        .mappings()
        .one_or_none()
    )


def review_eligible(session: Session, user_id: int, epoch: int, content_id: int) -> bool:
    return session.scalar(
        text(
            """SELECT EXISTS (SELECT 1 FROM sasu.watch_records
               WHERE user_id = :user AND learning_epoch = :epoch
                 AND content_id = :content AND completed_at IS NOT NULL)"""
        ),
        {"user": user_id, "epoch": epoch, "content": content_id},
    )


def wrong_eligible(session: Session, user_id: int, epoch: int, version_id: int) -> bool:
    return session.scalar(
        text(
            """SELECT EXISTS (SELECT 1 FROM sasu.wrong_answers
               WHERE user_id = :user AND learning_epoch = :epoch
                 AND quiz_version_id = :version AND status = 'UNRESOLVED')"""
        ),
        {"user": user_id, "epoch": epoch, "version": version_id},
    )


def insert_attempt(
    session: Session,
    attempt_id: UUID,
    user_id: int,
    epoch: int,
    question_id: int,
    version_id: int,
    context: str,
) -> None:
    session.execute(
        text(
            """INSERT INTO sasu.quiz_attempts
               (attempt_id, user_id, learning_epoch, quiz_id, quiz_version_id, context)
               VALUES (:id, :user, :epoch, :question, :version, :context)"""
        ),
        {
            "id": attempt_id,
            "user": user_id,
            "epoch": epoch,
            "question": question_id,
            "version": version_id,
            "context": context,
        },
    )


def lock_owned_attempt(session: Session, attempt_id: UUID, user_id: int, epoch: int):
    return (
        session.execute(
            text(
                """SELECT attempt_id, user_id, learning_epoch, quiz_id, quiz_version_id, context
                   FROM sasu.quiz_attempts
                   WHERE attempt_id = :id AND user_id = :user AND learning_epoch = :epoch
                   FOR UPDATE"""
            ),
            {"id": attempt_id, "user": user_id, "epoch": epoch},
        )
        .mappings()
        .one_or_none()
    )


def find_submission(session: Session, attempt_id: UUID):
    return (
        session.execute(
            text(
                """SELECT response_id, selected_option_id, result FROM sasu.quiz_responses
                   WHERE attempt_id = :id"""
            ),
            {"id": attempt_id},
        )
        .mappings()
        .one_or_none()
    )


def display_recorded(session: Session, attempt, content_id: int) -> bool:
    return session.scalar(
        text(
            """SELECT EXISTS (SELECT 1 FROM sasu.learning_events
               WHERE event_type = 'QUIZ_DISPLAYED' AND attempt_id = :attempt
                 AND user_id = :user AND learning_epoch = :epoch
                 AND quiz_version_id = :version AND content_id = :content)"""
        ),
        {
            "attempt": attempt["attempt_id"],
            "user": attempt["user_id"],
            "epoch": attempt["learning_epoch"],
            "version": attempt["quiz_version_id"],
            "content": content_id,
        },
    )


def insert_response(
    session: Session, attempt_id: UUID, version_id: int, option_id: int | None, result: str
) -> int:
    # 채점 결과는 DB가 다시 검증한다. 오답 추가·횟수 증가·해결은 AFTER INSERT 트리거가 맡는다.
    return session.scalar(
        text(
            """INSERT INTO sasu.quiz_responses
               (attempt_id, quiz_version_id, selected_option_id, result)
               VALUES (:attempt, :version, :option, :result) RETURNING response_id"""
        ),
        {"attempt": attempt_id, "version": version_id, "option": option_id, "result": result},
    )
