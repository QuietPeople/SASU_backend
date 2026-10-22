"""파트 4 조회 계약. 비율은 기존 관리자 API와 같은 percent(0~100) 단위."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.api.schemas import PageQuery
from app.core.types import MAX_BIGINT
from app.modules.admin.schemas import Rate, ReactionStats


class QuizStats(BaseModel):
    context: str
    displayed_count: int
    answered_count: int
    correct_count: int
    wrong_count: int
    skipped_count: int
    unanswered_display_count: int
    response_without_display_count: int
    accuracy: Rate
    participation: Rate
    skip_rate: Rate


class VideoQuizStats(QuizStats):
    first_accuracy: Rate


class WrongReviewStats(QuizStats):
    current_unresolved_count: int
    resolved_version_count: int


class FlashcardStats(BaseModel):
    opened_count: int
    revealed_count: int
    opened_users: int
    revealed_users: int


class ContentStatistics(BaseModel):
    content_id: int
    reactions: ReactionStats
    quiz: VideoQuizStats
    feed_review: QuizStats
    wrong_review: WrongReviewStats
    flashcards: FlashcardStats


class Overview(BaseModel):
    learner_count: int
    content_count: int
    published_content_count: int
    curriculum_count: int
    view_count: int
    like_count: int
    saved_count: int
    watch_completion: Rate
    first_quiz_accuracy: Rate


class ResponseQuery(PageQuery):
    user_id: int | None = Field(default=None, gt=0, le=MAX_BIGINT)
    content_id: int | None = Field(default=None, gt=0, le=MAX_BIGINT)
    quiz_version_id: int | None = Field(default=None, gt=0, le=MAX_BIGINT)
    context: Literal["VIDEO_END", "FEED_REVIEW", "WRONG_REVIEW"] | None = None
    result: Literal["CORRECT", "WRONG", "SKIPPED"] | None = None
    submitted_from: datetime | None = None
    submitted_to: datetime | None = None

    @model_validator(mode="after")
    def time_range(self):
        for value in (self.submitted_from, self.submitted_to):
            if value is not None and value.utcoffset() is None:
                raise ValueError("조회 시각에는 시간대가 필요합니다.")
        if self.submitted_from and self.submitted_to and self.submitted_from >= self.submitted_to:
            raise ValueError("시작 시각은 종료 시각보다 이전이어야 합니다.")
        return self


class ResponseItem(BaseModel):
    response_id: int
    attempt_id: UUID
    user_id: int
    content_id: int
    quiz_id: int
    quiz_version_id: int
    selected_option_id: int | None
    context: str
    result: str
    submitted_at: datetime


class ContentMetricItem(BaseModel):
    content_id: int
    title: str | None
    status: Literal["DRAFT", "PUBLISHED"]
    view_count: int
    like_count: int
    saved_count: int
