"""학습자는 본인만, 관리자는 대상 학습자의 현황을 조회한다."""

from app.core.exceptions import ApiError
from app.modules.dashboard import repository
from app.modules.dashboard.schemas import CategoryDashboard, Dashboard
from app.modules.statistics.service import rate


def check_target(actor, user_id):
    if actor.role != "ADMIN" and actor.user_id != user_id:
        raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")


def summary(session, user_id, actor):
    check_target(actor, user_id)
    row = repository.summary(session, user_id)
    if row is None:
        raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")
    return Dashboard(
        **{k: row[k] for k in Dashboard.model_fields if k != "first_quiz_accuracy"},
        first_quiz_accuracy=rate(row["first_correct"], row["first_answered"]),
    )


def categories(session, user_id, actor):
    check_target(actor, user_id)
    row = repository.categories(session, user_id)
    if row is None:
        raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")
    items = []
    for item in row["items"]:
        state = (
            "NEEDS_REVIEW"
            if item["current_wrong_count"]
            else "NO_CURRENT_ERRORS"
            if item["watched_count"] or item["answered_content_count"]
            else "NOT_STARTED"
        )
        items.append({**item, "state": state})
    return CategoryDashboard(
        user_id=user_id, record_generation=row["record_generation"], items=items
    )
