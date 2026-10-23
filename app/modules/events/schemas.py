from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.exceptions import ApiError
from app.core.types import PositiveId

EventType = Literal[
    "VIDEO_QUIZ_SHOWN",
    "FEED_REVIEW_SHOWN",
    "FLASHCARD_VIEWED",
    "FLASHCARD_FLIPPED",
    "PLAY_ERROR",
    "SEARCH_EMPTY",
]
DISPLAY_EVENTS = {"VIDEO_QUIZ_SHOWN", "FEED_REVIEW_SHOWN"}
CARD_EVENTS = {"FLASHCARD_VIEWED", "FLASHCARD_FLIPPED"}


class LearningEventBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_event_id: UUID
    event_type: EventType
    attempt_id: UUID | None = None
    content_id: Annotated[PositiveId, Field(strict=True)] | None = None
    question_version_id: Annotated[PositiveId, Field(strict=True)] | None = None
    error_code: str | None = None

    @model_validator(mode="after")
    def validate_relation(self) -> "LearningEventBody":
        invalid = False
        if self.event_type in DISPLAY_EVENTS:
            invalid = self.attempt_id is None
        else:
            invalid = self.attempt_id is not None
            if self.event_type in CARD_EVENTS:
                invalid |= self.content_id is None or self.question_version_id is None
            elif self.event_type == "PLAY_ERROR":
                invalid |= self.content_id is None or self.question_version_id is not None
            else:
                invalid |= self.content_id is not None or self.question_version_id is not None
        invalid |= self.error_code is not None and self.event_type != "PLAY_ERROR"
        if invalid:
            raise ApiError(
                422, "INVALID_EVENT_RELATION", "이벤트 종류와 대상 정보가 일치하지 않습니다."
            )
        return self


class LearningEvent(BaseModel):
    # 확정 DB의 event_id는 UUID다. 별도 숫자 식별자를 임의로 만들지 않는다.
    event_id: UUID
    client_event_id: UUID
    event_type: EventType
    occurred_at: datetime
    recorded: bool
