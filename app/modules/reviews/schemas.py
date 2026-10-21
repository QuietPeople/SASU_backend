"""복습 조회 필터와 학습자용 응답 계약."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.schemas import PageQuery
from app.core.types import PositiveId
from app.modules.contents.schemas import CategorySummary, ContentSummary
from app.modules.questions.schemas import LearnerQuestion


class ReviewListQuery(PageQuery):
    category_id: PositiveId | None = None


class WrongAnswerQuery(ReviewListQuery):
    status: Literal["PENDING", "RESOLVED"] = "PENDING"


class CandidateFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    shown_question_version_ids: list[PositiveId] = Field(max_length=1000)
    retry_question_version_ids: list[PositiveId] = Field(max_length=1000)

    @field_validator("shown_question_version_ids", "retry_question_version_ids")
    @classmethod
    def deduplicate(cls, values: list[int]) -> list[int]:
        return sorted(set(values))


class ReviewCandidate(BaseModel):
    candidate: LearnerQuestion | None
    record_generation: int


class WrongAnswerItem(BaseModel):
    question: LearnerQuestion
    content: ContentSummary
    status: Literal["PENDING", "RESOLVED"]
    wrong_count: int
    first_wrong_at: datetime
    last_wrong_at: datetime
    resolved_at: datetime | None


class Flashcard(BaseModel):
    question_id: int
    question_version_id: int
    content_id: int
    content_title: str
    category: CategorySummary
    front: str


class FlashcardDetail(BaseModel):
    card: Flashcard
    back: str
    explanation: str
