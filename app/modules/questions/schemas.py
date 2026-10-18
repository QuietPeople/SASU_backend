"""외부 question/MCQ_3 명칭과 DB quiz/MCQ3를 구분한다."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.security import MAX_BIGINT

QuestionType = Literal["OX", "MCQ_3", "MCQ_4"]
PositiveId = Annotated[int, Field(gt=0, le=MAX_BIGINT)]


class OptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    option_order: int = Field(ge=1, le=4)
    option_text: str = Field(min_length=1)
    is_correct: bool


class QuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    question_type: QuestionType = "MCQ_3"
    question_text: str = Field(min_length=1)
    options: list[OptionInput]
    explanation: str = Field(min_length=1)


class VersionInput(QuestionInput):
    expected_current_version_id: PositiveId
    question_type: QuestionType


class LearnerOption(BaseModel):
    option_id: int
    option_order: int
    option_text: str


class EditorOption(LearnerOption):
    is_correct: bool


class LearnerQuestion(BaseModel):
    question_id: int
    question_version_id: int
    content_id: int
    question_type: QuestionType
    question_text: str
    options: list[LearnerOption]


class QuestionVersion(BaseModel):
    question_id: int
    question_version_id: int
    content_id: int
    version_no: int
    question_type: QuestionType
    question_text: str
    options: list[EditorOption]
    explanation: str
    created_at: datetime
    is_current: bool


class VersionSummary(BaseModel):
    question_id: int
    question_version_id: int
    version_no: int
    is_current: bool
    created_at: datetime
    response_count: int
