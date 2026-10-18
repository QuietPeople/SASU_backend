"""최초 제출 결과와 조회 시점의 오답 상태를 구분하는 응답 계약."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.modules.questions.schemas import LearnerQuestion


class WrongState(BaseModel):
    question_version_id: int
    status: Literal["PENDING", "RESOLVED"]
    wrong_count: int
    resolved_at: datetime | None


class ResponseDetail(BaseModel):
    response_id: int
    attempt_id: UUID | None
    user_id: int
    question: LearnerQuestion
    response_path: Literal["VIDEO_QUIZ", "FEED_REVIEW", "WRONG_NOTE"]
    result: Literal["CORRECT", "WRONG", "SKIP"]
    selected_option_id: int | None
    correct_option_id: int
    correct_answer: str
    explanation: str
    submitted_at: datetime
    wrong_state: WrongState | None
