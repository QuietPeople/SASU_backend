"""복습 자료 조회. 풀이·노출·응답·오답을 생성하거나 변경하지 않는다."""

from sqlalchemy.orm import Session

from app.api.schemas import Page
from app.core.exceptions import ApiError
from app.modules.contents.presentation import build_summary
from app.modules.questions.schemas import LearnerQuestion
from app.modules.questions.service import get_version
from app.modules.reviews import repository
from app.modules.reviews.schemas import (
    CandidateFilter,
    Flashcard,
    FlashcardDetail,
    ReviewCandidate,
    ReviewListQuery,
    WrongAnswerItem,
    WrongAnswerQuery,
)
from app.modules.users.service import require_learner
from app.modules.users.settings_service import current_epoch
from app.modules.videos.availability import is_video_row_available


def read_epoch(session: Session, actor_id: int, user_id: int) -> int:
    require_learner(session, actor_id, user_id)
    # 초기화·응답 저장과 조회가 섞이지 않도록 기존 사용자 상태 잠금을 재사용한다.
    return current_epoch(session, user_id, write=False)


def check_category(session: Session, category_id: int | None) -> None:
    if category_id is not None and not repository.category_exists(session, category_id):
        raise ApiError(404, "CATEGORY_NOT_FOUND", "카테고리를 찾을 수 없습니다.")


def make_card(row) -> Flashcard:
    return Flashcard(
        question_id=row["question_id"],
        question_version_id=row["question_version_id"],
        content_id=row["content_id"],
        content_title=row["content_title"],
        category={"category_id": row["category_id"], "name": row["category_name"]},
        front=row["question_text"],
    )


def get_wrong_answers(
    session: Session, actor_id: int, user_id: int, query: WrongAnswerQuery
) -> Page[WrongAnswerItem]:
    epoch = read_epoch(session, actor_id, user_id)
    check_category(session, query.category_id)
    status = {"PENDING": "UNRESOLVED", "RESOLVED": "RESOLVED"}[query.status]
    rows, total = repository.list_wrong_answers(session, user_id, epoch, status, query)
    items = []
    for row in rows:
        items.append(
            WrongAnswerItem(
                question=LearnerQuestion(
                    question_id=row["question_id"],
                    question_version_id=row["question_version_id"],
                    content_id=row["content_id"],
                    question_type={"OX": "OX", "MCQ3": "MCQ_3", "MCQ4": "MCQ_4"}[
                        row["question_type"]
                    ],
                    question_text=row["question_text"],
                    options=row["options"],
                ),
                content=build_summary(
                    {**row, "title": row["content_title"], "has_quiz": True, "status": "PUBLISHED"},
                    actor_id,
                ),
                status=query.status,
                wrong_count=row["wrong_count"],
                first_wrong_at=row["first_wrong_at"],
                last_wrong_at=row["last_wrong_at"],
                resolved_at=row["resolved_at"],
            )
        )
    return Page[WrongAnswerItem](
        items=items,
        page=query.page,
        size=query.size,
        total=total,
        has_next=query.page * query.size < total,
    )


def get_flashcards(
    session: Session, actor_id: int, user_id: int, query: ReviewListQuery
) -> Page[Flashcard]:
    read_epoch(session, actor_id, user_id)
    check_category(session, query.category_id)
    rows, total = repository.list_flashcards(session, query)
    return Page[Flashcard](
        items=[make_card(row) for row in rows],
        page=query.page,
        size=query.size,
        total=total,
        has_next=query.page * query.size < total,
    )


def get_flashcard(
    session: Session, actor_id: int, user_id: int, version_id: int
) -> FlashcardDetail:
    read_epoch(session, actor_id, user_id)
    row = repository.find_flashcard(session, version_id)
    if row is None:
        raise ApiError(404, "FLASHCARD_NOT_FOUND", "공개된 플래시카드를 찾을 수 없습니다.")
    return FlashcardDetail(card=make_card(row), back=row["back"], explanation=row["explanation"])


def get_candidate(
    session: Session, actor_id: int, user_id: int, request: CandidateFilter
) -> ReviewCandidate:
    epoch = read_epoch(session, actor_id, user_id)
    retry = set(request.retry_question_version_ids)
    if not retry.issubset(request.shown_question_version_ids) or retry != repository.retry_versions(
        session, user_id, epoch, request.retry_question_version_ids
    ):
        raise ApiError(
            422, "INVALID_REVIEW_FILTER", "재출제 대상과 본인의 복습 오답 이력을 확인해 주세요."
        )
    for row in repository.feed_candidates(
        session,
        user_id,
        epoch,
        request.shown_question_version_ids,
        request.retry_question_version_ids,
    ):
        # 이용 불가 영상을 건너뛰어 ATM-01에서 바로 사용할 수 있는 후보를 고른다.
        if is_video_row_available(row):
            version = get_version(session, row["quiz_id"], row["quiz_version_id"])
            return ReviewCandidate(
                candidate=LearnerQuestion.model_validate(version.model_dump()),
                record_generation=epoch - 1,
            )
    return ReviewCandidate(candidate=None, record_generation=epoch - 1)
