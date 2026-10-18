"""커리큘럼 API 계약. 단계 키는 과정 안의 content_id로 대응한다."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.schemas import PageQuery, ViewQuery
from app.core.security import MAX_BIGINT

PositiveId = Annotated[int, Field(gt=0, le=MAX_BIGINT)]


class CurriculumQuery(ViewQuery):
    user_id: PositiveId | None = None


class CurriculumListQuery(CurriculumQuery, PageQuery):
    pass


class CurriculumInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=100)
    description: str | None = None


class CurriculumPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set or ("title" in self.model_fields_set and self.title is None):
            raise ValueError("변경할 필드가 필요하며 제목은 null로 비울 수 없습니다.")
        return self


class StepsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    content_ids: list[PositiveId]


class Category(BaseModel):
    category_id: int
    name: str


class Tag(BaseModel):
    tag_id: int
    name: str


class ContentSummary(BaseModel):
    content_id: int
    title: str | None
    category: Category | None
    tags: list[Tag]
    video_duration: float | None
    video_url: str | None
    media_revision: str | None
    view_count: int
    like_count: int
    liked: bool | None
    saved: bool | None
    watch_completed: bool | None
    has_quiz: bool
    status: Literal["DRAFT", "PUBLISHED"]


class CurriculumSummary(BaseModel):
    curriculum_id: int
    title: str
    description: str | None
    total_steps: int
    available_steps: int
    completed_steps: int | None
    progress_percent: float | None


class ProgressStep(BaseModel):
    curriculum_content_id: int
    content_id: int
    step_order: int
    watch_completed: bool | None
    question_correct: bool | None
    completed: bool | None


class CurriculumStep(ProgressStep):
    content: ContentSummary | None
    available: bool


class CurriculumDetail(BaseModel):
    summary: CurriculumSummary
    steps: list[CurriculumStep]


class CurriculumSteps(BaseModel):
    items: list[CurriculumStep]
    total_steps: int


class CurriculumProgress(BaseModel):
    user_id: int
    curriculum_id: int
    total_steps: int
    completed_steps: int
    progress_percent: float | None
    steps: list[ProgressStep]
