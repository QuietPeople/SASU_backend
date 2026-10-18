"""제출 버전으로 결과를 복원하며 재채점·오답 갱신을 수행하지 않는다."""

from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.core.security import Actor
from app.modules.questions.schemas import LearnerOption, LearnerQuestion
from app.modules.questions.service import get_version
from app.modules.responses import repository
from app.modules.responses.schemas import ResponseDetail, WrongState


def get_response(session: Session, response_id: int, actor: Actor) -> ResponseDetail:
    record = repository.find_response(session, response_id, actor)
    if record is None:
        raise ApiError(404, "RESPONSE_NOT_FOUND", "응답을 찾을 수 없습니다.")
    version = get_version(session, record["question_id"], record["question_version_id"])
    correct = next(option for option in version.options if option.is_correct)
    question = LearnerQuestion(
        question_id=version.question_id,
        question_version_id=version.question_version_id,
        content_id=version.content_id,
        question_type=version.question_type,
        question_text=version.question_text,
        options=[LearnerOption.model_validate(option.model_dump()) for option in version.options],
    )
    wrong_state = None
    if record["wrong_status"] is not None:
        wrong_state = WrongState(
            question_version_id=version.question_version_id,
            status={"UNRESOLVED": "PENDING", "RESOLVED": "RESOLVED"}[record["wrong_status"]],
            wrong_count=record["wrong_count"],
            resolved_at=record["resolved_at"],
        )
    return ResponseDetail(
        response_id=record["response_id"],
        attempt_id=record["attempt_id"],
        user_id=record["user_id"],
        question=question,
        response_path={
            "VIDEO_END": "VIDEO_QUIZ",
            "FEED_REVIEW": "FEED_REVIEW",
            "WRONG_REVIEW": "WRONG_NOTE",
        }[record["context"]],
        result={"CORRECT": "CORRECT", "WRONG": "WRONG", "SKIPPED": "SKIP"}[record["result"]],
        selected_option_id=record["selected_option_id"],
        correct_option_id=correct.option_id,
        correct_answer=correct.option_text,
        explanation=version.explanation,
        submitted_at=record["submitted_at"],
        wrong_state=wrong_state,
    )
