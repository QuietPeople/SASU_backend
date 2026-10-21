"""퀴즈 형식 검증과 문항 수정 이력 보존."""

from sqlalchemy.orm import Session

from app.api.schemas import Page, PageQuery
from app.core.exceptions import ApiError
from app.core.security import Actor
from app.modules.questions import repository
from app.modules.questions.schemas import (
    LearnerOption,
    LearnerQuestion,
    QuestionInput,
    QuestionVersion,
    VersionInput,
    VersionSummary,
)


def validate_options(request: QuestionInput | QuestionVersion) -> None:
    count = {"OX": 2, "MCQ_3": 3, "MCQ_4": 4}[request.question_type]
    options = sorted(request.options, key=lambda option: option.option_order)
    if (
        len(options) != count
        or [option.option_order for option in options] != list(range(1, count + 1))
        or sum(option.is_correct for option in options) != 1
        or (
            request.question_type == "OX"
            and [option.option_text for option in options] != ["O", "X"]
        )
    ):
        raise ApiError(422, "INVALID_OPTION", "보기 수·순서·정답 수와 O/X 문구를 확인해 주세요.")


def get_version(session: Session, question_id: int, version_id: int) -> QuestionVersion:
    header = repository.version_header(session, question_id, version_id)
    if header is None:
        raise ApiError(404, "QUESTION_VERSION_NOT_FOUND", "해당 문항의 버전을 찾을 수 없습니다.")
    data = dict(header)
    data["question_type"] = {"OX": "OX", "MCQ3": "MCQ_3", "MCQ4": "MCQ_4"}[data["question_type"]]
    return QuestionVersion(**data, options=repository.version_options(session, version_id))


def get_current(session: Session, content_id: int, view: str, actor: Actor):
    if view == "editor" and actor.role != "ADMIN":
        raise ApiError(403, "EDITOR_VIEW_REQUIRED", "관리자 편집 조회가 필요합니다.")
    content = repository.find_content(session, content_id)
    if content is None or (view == "learner" and content["status"] != "PUBLISHED"):
        raise ApiError(404, "CONTENT_NOT_FOUND", "콘텐츠를 찾을 수 없습니다.")
    question = repository.question_for_content(session, content_id)
    if question is None:
        return None
    version = get_version(session, question["quiz_id"], question["current_version_id"])
    return LearnerQuestion(
        **version.model_dump(
            exclude={"options", "explanation", "created_at", "is_current", "version_no"}
        ),
        options=[LearnerOption.model_validate(option.model_dump()) for option in version.options],
    )


def register_question(session: Session, content_id: int, request: QuestionInput) -> QuestionVersion:
    try:
        validate_options(request)
        if repository.find_content(session, content_id, lock=True) is None:
            raise ApiError(404, "CONTENT_NOT_FOUND", "콘텐츠를 찾을 수 없습니다.")
        if repository.question_for_content(session, content_id) is not None:
            raise ApiError(409, "QUESTION_ALREADY_EXISTS", "이미 퀴즈가 등록되어 있습니다.")
        question_id = repository.create_question(session, content_id)
        version_id = repository.create_version(session, question_id, 1, request)
        repository.create_options(session, version_id, request.options)
        repository.set_current_version(session, question_id, version_id)
        result = get_version(session, question_id, version_id)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


def revise_question(session: Session, question_id: int, request: VersionInput) -> QuestionVersion:
    try:
        validate_options(request)
        question = repository.find_question(session, question_id, lock=True)
        if question is None:
            raise ApiError(404, "QUESTION_NOT_FOUND", "문항을 찾을 수 없습니다.")
        if question["current_version_id"] != request.expected_current_version_id:
            raise ApiError(409, "VERSION_CONFLICT", "현재 문항 버전을 다시 확인해 주세요.")
        current = repository.version_header(session, question_id, question["current_version_id"])
        version_id = repository.create_version(
            session, question_id, current["version_no"] + 1, request
        )
        repository.create_options(session, version_id, request.options)
        repository.set_current_version(session, question_id, version_id)
        result = get_version(session, question_id, version_id)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


def get_versions(session: Session, question_id: int, query: PageQuery) -> Page[VersionSummary]:
    if repository.find_question(session, question_id) is None:
        raise ApiError(404, "QUESTION_NOT_FOUND", "문항을 찾을 수 없습니다.")
    rows, total = repository.list_versions(session, question_id, query.page, query.size)
    return Page[VersionSummary](
        items=list(rows),
        page=query.page,
        size=query.size,
        total=total,
        has_next=query.page * query.size < total,
    )
