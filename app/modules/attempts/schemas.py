"""ATM 요청·응답. 제출 전에는 학습자용 문항만 제공한다."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.types import PositiveId
from app.modules.questions.schemas import LearnerQuestion
from app.modules.responses.schemas import ResponseDetail

ResponsePath = Literal["VIDEO_QUIZ", "FEED_REVIEW", "WRONG_NOTE"]


class AttemptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: UUID
    question_id: Annotated[PositiveId, Field(strict=True)]
    expected_question_version_id: Annotated[PositiveId, Field(strict=True)]
    response_path: ResponsePath


class Attempt(BaseModel):
    attempt_id: UUID
    user_id: int
    question: LearnerQuestion
    response_path: ResponsePath
    created_at: datetime
    submitted: bool
    response: ResponseDetail | None
    record_generation: int


class AttemptSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: Literal["ANSWER", "SKIP"]
    selected_option_id: PositiveId | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> "AttemptSubmission":
        if self.action == "ANSWER" and self.selected_option_id is None:
            raise ValueError("답변에는 selected_option_id가 필요합니다.")
        if self.action == "SKIP" and self.selected_option_id is not None:
            raise ValueError("건너뛰기에는 selected_option_id를 지정할 수 없습니다.")
        return self
