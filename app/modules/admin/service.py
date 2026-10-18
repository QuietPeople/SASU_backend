"""통계 계산과 테스트 초기화의 트랜잭션 경계를 관리한다."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.admin import repository
from app.modules.admin.schemas import (
    DeletedCounts,
    Rate,
    ReactionStats,
    ResetRequest,
    ResetResult,
)


def get_reaction_stats(session: Session, content_id: int) -> ReactionStats:
    stats = repository.find_reaction_stats(session, content_id)
    if stats is None:
        raise ApiError(404, "CONTENT_NOT_FOUND", "콘텐츠를 찾을 수 없습니다.")
    completed = stats["completed_count"]
    played = stats["played_count"]
    percent = float(round(Decimal(completed) * 100 / played, 2)) if played else None
    return ReactionStats(
        view_count=stats["view_count"],
        like_count=stats["like_count"],
        saved_count=stats["saved_count"],
        watch_completion=Rate(numerator=completed, denominator=played, percent=percent),
    )


def reset_records(session: Session, user_id: int, request: ResetRequest) -> ResetResult:
    try:
        if not request.confirm:
            raise ApiError(422, "RESET_CONFIRMATION_REQUIRED", "초기화 확인이 필요합니다.")
        state = repository.lock_learner_state(session, user_id)
        if state is None:
            raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")
        expected_epoch = request.expected_record_generation + 1
        if state["learning_epoch"] != expected_epoch:
            raise ApiError(
                409, "RECORD_GENERATION_MISMATCH", "현재 기록 세대를 다시 확인해 주세요."
            )
        deleted = DeletedCounts.model_validate(repository.count_learning_records(session, user_id))
        next_epoch = repository.reset_learning(session, user_id, expected_epoch)
        result = ResetResult(
            user_id=user_id,
            record_generation=next_epoch - 1,
            deleted_counts=deleted,
            clear_client_feed_state=True,
            preserved=[
                "users",
                "interests",
                "interest_guide_completed",
                "review_interval",
                "contents",
                "questions",
                "question_versions",
                "curriculums",
                "video_files",
            ],
        )
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
