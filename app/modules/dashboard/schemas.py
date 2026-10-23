from typing import Literal

from pydantic import BaseModel

from app.modules.admin.schemas import Rate


class CategoryStatus(BaseModel):
    category: dict[str, int | str]
    pending_question_count: int
    state: Literal["NEEDS_REVIEW", "NO_PENDING_WRONG"]


class CourseProgress(BaseModel):
    curriculum_id: int
    title: str
    description: str | None
    total_steps: int
    available_steps: int
    completed_steps: int
    progress_percent: float | None


class Dashboard(BaseModel):
    user_id: int
    watched_content_count: int
    completed_content_count: int
    answered_count: int
    pending_question_count: int
    first_quiz_accuracy: Rate
    category_states: list[CategoryStatus]
    curriculums: list[CourseProgress]


class CategoryDashboard(BaseModel):
    items: list[CategoryStatus]
