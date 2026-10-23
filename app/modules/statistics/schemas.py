from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas import PageQuery
from app.core.types import MAX_BIGINT
from app.modules.admin.schemas import Rate, ReactionStats


class VideoQuizStats(BaseModel):
    shown_count: int
    answered_count: int
    skipped_count: int
    participation: Rate
    first_accuracy: Rate


class FeedReviewStats(BaseModel):
    shown_count: int
    answered_count: int
    skipped_count: int
    response_rate: Rate
    accuracy: Rate


class WrongReviewStats(BaseModel):
    answered_count: int
    accuracy: Rate
    pending_count: int
    resolved_count: int


class FlashcardStats(BaseModel):
    viewed_count: int
    flipped_count: int


class ContentStatistics(BaseModel):
    content_id: int
    title: str | None
    reactions: ReactionStats
    quiz: VideoQuizStats
    feed_review: FeedReviewStats
    wrong_review: WrongReviewStats
    flashcards: FlashcardStats


class Overview(BaseModel):
    content_count: int
    published_content_count: int
    reactions: ReactionStats
    quiz: VideoQuizStats
    feed_review: FeedReviewStats
    wrong_review: WrongReviewStats
    flashcards: FlashcardStats


class ContentQuery(PageQuery):
    category_id: int | None = Field(default=None, gt=0, le=MAX_BIGINT)
    status: Literal["DRAFT", "PUBLISHED", "ALL"] = "ALL"


class ResponseQuery(PageQuery):
    user_id: int | None = Field(default=None, gt=0, le=MAX_BIGINT)
    content_id: int | None = Field(default=None, gt=0, le=MAX_BIGINT)
    question_id: int | None = Field(default=None, gt=0, le=MAX_BIGINT)
    question_version_id: int | None = Field(default=None, gt=0, le=MAX_BIGINT)
    response_path: Literal["VIDEO_QUIZ", "FEED_REVIEW", "WRONG_NOTE"] | None = None
    result: Literal["CORRECT", "WRONG", "SKIP"] | None = None
