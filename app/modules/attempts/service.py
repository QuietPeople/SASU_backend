"""풀이 ID 멱등성·버전 고정·복습 자격·초기화와의 원자성을 관리한다."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.core.security import Actor
from app.integrations.storage import LocalVideoStorage
from app.modules.attempts import repository
from app.modules.attempts.schemas import Attempt, AttemptCreate, AttemptSubmission
from app.modules.questions.schemas import LearnerQuestion
from app.modules.questions.service import get_version, validate_options
from app.modules.responses.schemas import ResponseDetail
from app.modules.responses.service import get_response
from app.modules.users.service import get_actor

CONTEXTS = {"VIDEO_QUIZ": "VIDEO_END", "FEED_REVIEW": "FEED_REVIEW", "WRONG_NOTE": "WRONG_REVIEW"}
RESPONSE_PATHS = {value: key for key, value in CONTEXTS.items()}


def check_learner(session: Session, actor_id: int, user_id: int) -> None:
    actor = get_actor(session, actor_id)
    if actor.role != "LEARNER":
        raise ApiError(403, "ROLE_NOT_ALLOWED", "학습자만 풀이를 이용할 수 있습니다.")
    if actor.user_id != user_id:
        raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")


def current_epoch(session: Session, user_id: int, *, write: bool) -> int:
    epoch = repository.learner_epoch(session, user_id, write=write)
    if epoch is None:
        raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")
    return epoch


def make_attempt(session: Session, record) -> Attempt:
    version = get_version(session, record["quiz_id"], record["quiz_version_id"])
    response_id = record["response_id"]
    return Attempt(
        attempt_id=record["attempt_id"],
        user_id=record["user_id"],
        question=LearnerQuestion.model_validate(version.model_dump()),
        response_path=RESPONSE_PATHS[record["context"]],
        created_at=record["created_at"],
        submitted=response_id is not None,
        response=get_response(session, response_id, Actor(record["user_id"], "LEARNER"))
        if response_id is not None
        else None,
        record_generation=record["learning_epoch"] - 1,
    )


def media_available(relative_path: str | None) -> bool:
    if not relative_path:
        return False
    try:
        return (
            LocalVideoStorage(get_settings().video_storage_root)
            .resolve_path(relative_path)
            .is_file()
        )
    except (OSError, RuntimeError, ValueError):
        return False


def create_attempt(
    session: Session, actor_id: int, user_id: int, record_generation: int, request: AttemptCreate
) -> tuple[Attempt, bool]:
    try:
        check_learner(session, actor_id, user_id)
        epoch = current_epoch(session, user_id, write=True)
        if epoch != record_generation + 1:
            raise ApiError(
                409, "RECORD_GENERATION_MISMATCH", "현재 기록 세대를 다시 확인해 주세요."
            )
        repository.lock_attempt_id(session, request.attempt_id)
        existing = repository.find_attempt(session, request.attempt_id)
        if existing is not None:
            if (
                existing["user_id"],
                existing["learning_epoch"],
                existing["quiz_id"],
                existing["quiz_version_id"],
                existing["context"],
            ) != (
                user_id,
                epoch,
                request.question_id,
                request.expected_question_version_id,
                CONTEXTS[request.response_path],
            ):
                raise ApiError(409, "ATTEMPT_ID_CONFLICT", "다른 입력에 사용된 풀이 ID입니다.")
            result = make_attempt(session, existing)
            session.commit()
            return result, False

        content_id = repository.question_content_id(session, request.question_id)
        content = repository.lock_content(session, content_id) if content_id is not None else None
        if (
            content is None
            or content["status"] != "PUBLISHED"
            or not media_available(content["storage_path"])
        ):
            raise ApiError(404, "QUESTION_NOT_FOUND", "이용 가능한 문항을 찾을 수 없습니다.")
        question = repository.lock_question(session, request.question_id)
        if question is None or question["current_version_id"] is None:
            raise ApiError(404, "QUESTION_NOT_FOUND", "이용 가능한 문항을 찾을 수 없습니다.")
        if question["current_version_id"] != request.expected_question_version_id:
            raise ApiError(409, "VERSION_CONFLICT", "현재 문항 버전을 다시 확인해 주세요.")
        eligible = True
        if request.response_path == "FEED_REVIEW":
            eligible = repository.review_eligible(session, user_id, epoch, content_id)
        elif request.response_path == "WRONG_NOTE":
            eligible = repository.wrong_eligible(
                session, user_id, epoch, question["current_version_id"]
            )
        if not eligible:
            raise ApiError(
                409, "ATTEMPT_NOT_ELIGIBLE", "현재 풀이 경로의 이용 조건을 만족하지 않습니다."
            )
        repository.insert_attempt(
            session,
            request.attempt_id,
            user_id,
            epoch,
            request.question_id,
            question["current_version_id"],
            CONTEXTS[request.response_path],
        )
        result = make_attempt(session, repository.find_attempt(session, request.attempt_id))
        session.commit()
        return result, True
    except Exception:
        session.rollback()
        raise


def recover_attempt(session: Session, actor_id: int, user_id: int, attempt_id: UUID) -> Attempt:
    check_learner(session, actor_id, user_id)
    epoch = current_epoch(session, user_id, write=False)
    record = repository.find_attempt(session, attempt_id)
    if record is None or record["user_id"] != user_id or record["learning_epoch"] != epoch:
        raise ApiError(404, "ATTEMPT_NOT_FOUND", "본인의 현재 세대 풀이를 찾을 수 없습니다.")
    return make_attempt(session, record)


def submit_response(
    session: Session,
    actor_id: int,
    user_id: int,
    attempt_id: UUID,
    record_generation: int,
    request: AttemptSubmission,
) -> ResponseDetail:
    try:
        check_learner(session, actor_id, user_id)
        epoch = current_epoch(session, user_id, write=True)
        if epoch != record_generation + 1:
            raise ApiError(
                409, "RECORD_GENERATION_MISMATCH", "현재 기록 세대를 다시 확인해 주세요."
            )
        attempt = repository.lock_owned_attempt(session, attempt_id, user_id, epoch)
        if attempt is None:
            raise ApiError(404, "ATTEMPT_NOT_FOUND", "본인의 현재 세대 풀이를 찾을 수 없습니다.")
        existing = repository.find_submission(session, attempt_id)
        actor = Actor(user_id, "LEARNER")
        if existing is not None:
            if (existing["result"] == "SKIPPED") != (request.action == "SKIP") or existing[
                "selected_option_id"
            ] != request.selected_option_id:
                raise ApiError(409, "ALREADY_SUBMITTED", "이미 다른 답변으로 제출한 풀이입니다.")
            result = get_response(session, existing["response_id"], actor)
            session.commit()
            return result

        # 현재 버전으로 바꾸지 않는다. 생성 당시 버전은 DB에서 불변으로 보존된다.
        version = get_version(session, attempt["quiz_id"], attempt["quiz_version_id"])
        content = repository.lock_content(session, version.content_id)
        if (
            content is None
            or content["status"] != "PUBLISHED"
            or not media_available(content["storage_path"])
        ):
            raise ApiError(404, "CONTENT_NOT_FOUND", "이용 가능한 콘텐츠를 찾을 수 없습니다.")
        validate_options(version)
        verdict = "SKIPPED"
        if request.action == "ANSWER":
            option = next(
                (item for item in version.options if item.option_id == request.selected_option_id),
                None,
            )
            if option is None:
                raise ApiError(422, "INVALID_OPTION", "해당 풀이 버전의 보기를 선택해 주세요.")
            verdict = "CORRECT" if option.is_correct else "WRONG"
        if attempt["context"] in {"VIDEO_END", "FEED_REVIEW"} and not repository.display_recorded(
            session, attempt, version.content_id
        ):
            raise ApiError(409, "DISPLAY_NOT_RECORDED", "문항 노출 기록 후 다시 제출해 주세요.")
        response_id = repository.insert_response(
            session, attempt_id, version.question_version_id, request.selected_option_id, verdict
        )
        result = get_response(session, response_id, actor)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
