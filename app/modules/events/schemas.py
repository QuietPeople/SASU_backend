from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

EventType = Literal["QUIZ_DISPLAYED", "CARD_OPENED", "CARD_REVEALED", "PLAYBACK_ERROR", "SEARCH_EMPTY"]

_NEEDS_CONTENT = {"QUIZ_DISPLAYED", "CARD_OPENED", "CARD_REVEALED", "PLAYBACK_ERROR"}
_NEEDS_VERSION = {"QUIZ_DISPLAYED", "CARD_OPENED", "CARD_REVEALED"}
_NEEDS_ATTEMPT = {"QUIZ_DISPLAYED"}


class LearningEventBody(BaseModel):
    event_type: EventType
    content_id: int | None = Field(default=None, description="관련 콘텐츠 ID")
    quiz_version_id: int | None = Field(default=None, description="관련 퀴즈 버전 ID")
    attempt_id: UUID | None = Field(default=None, description="관련 풀이 UUID")
    metadata: dict = Field(default_factory=dict, description="부가 정보(오류 코드 등)")

    @model_validator(mode="after")
    def validate_fields_for_type(self) -> "LearningEventBody":
        t = self.event_type
        if t in _NEEDS_CONTENT and self.content_id is None:
            raise ValueError(f"{t} 이벤트는 content_id가 필요합니다.")
        if t not in _NEEDS_CONTENT and self.content_id is not None:
            raise ValueError(f"{t} 이벤트는 content_id를 허용하지 않습니다.")
        if t in _NEEDS_VERSION and self.quiz_version_id is None:
            raise ValueError(f"{t} 이벤트는 quiz_version_id가 필요합니다.")
        if t not in _NEEDS_VERSION and self.quiz_version_id is not None:
            raise ValueError(f"{t} 이벤트는 quiz_version_id를 허용하지 않습니다.")
        if t in _NEEDS_ATTEMPT and self.attempt_id is None:
            raise ValueError(f"{t} 이벤트는 attempt_id가 필요합니다.")
        if t not in _NEEDS_ATTEMPT and self.attempt_id is not None:
            raise ValueError(f"{t} 이벤트는 attempt_id를 허용하지 않습니다.")
        return self
