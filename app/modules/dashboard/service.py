from app.core.exceptions import ApiError
from app.modules.curricula.service import media_available
from app.modules.dashboard import repository
from app.modules.dashboard.schemas import CategoryDashboard, Dashboard
from app.modules.statistics.service import rate


def check_target(actor, user_id):
    if actor.role != "ADMIN" and actor.user_id != user_id:
        raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")


def category_items(items):
    return [
        dict(
            category={"category_id": i["category_id"], "name": i["name"]},
            pending_question_count=i["current_wrong_count"],
            state="NEEDS_REVIEW" if i["current_wrong_count"] else "NO_PENDING_WRONG",
        )
        for i in items
    ]


def summary(session, user_id, actor):
    check_target(actor, user_id)
    row = repository.summary(session, user_id)
    if row is None:
        raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")
    courses = []
    for course in row["curriculums"]:
        course["available_steps"] = sum(
            media_available(path) for path in course.pop("media_paths", []) or []
        )
        courses.append(course)
    return Dashboard(
        user_id=user_id,
        watched_content_count=row["watched_content_count"],
        completed_content_count=row["completed_content_count"],
        answered_count=row["answered_count"],
        pending_question_count=row["current_wrong_count"],
        first_quiz_accuracy=rate(row["first_correct"], row["first_answered"]),
        category_states=category_items(row["category_items"]),
        curriculums=courses,
    )


def categories(session, user_id, actor):
    check_target(actor, user_id)
    row = repository.categories(session, user_id)
    if row is None:
        raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")
    return CategoryDashboard(items=category_items(row["items"]))
