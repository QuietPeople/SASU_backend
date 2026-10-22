"""개인 학습 현황. 미해결 오답 없음은 숙달 판정이 아니다."""

from typing import Literal

from pydantic import BaseModel

from app.modules.admin.schemas import Rate


class CourseProgress(BaseModel):
    curriculum_id: int
    title: str
    total_steps: int
    completed_steps: int
    progress_percent: float | None


class Dashboard(BaseModel):
    user_id: int
    record_generation: int
    watched_count: int
    watch_completed_count: int
    liked_count: int
    saved_count: int
    answered_count: int
    skipped_count: int
    current_wrong_count: int
    first_quiz_accuracy: Rate
    in_progress_curriculums: list[CourseProgress]


class CategoryStatus(BaseModel):
    category_id: int
    name: str
    published_content_count: int
    watched_count: int
    completed_count: int
    answered_content_count: int
    current_wrong_count: int
    state: Literal["NOT_STARTED", "NEEDS_REVIEW", "NO_CURRENT_ERRORS"]


class CategoryDashboard(BaseModel):
    user_id: int
    record_generation: int
    items: list[CategoryStatus]
