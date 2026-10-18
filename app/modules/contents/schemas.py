from datetime import date
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator

ResourceId = Annotated[int, Field(gt=0, le=9223372036854775807)]
NonBlankText = Annotated[str, Field(min_length=1)]
Title = Annotated[str, Field(min_length=1, max_length=200)]
ContentStatus = Literal["DRAFT", "PUBLISHED"]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InputModel(ApiModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class ContentListQuery(InputModel):
    q: Annotated[str, Field(max_length=200)] | None = None
    category_id: ResourceId | None = None
    status: Literal["DRAFT", "PUBLISHED", "ALL"] | None = Field(
        default=None, description="생략 시 역할에 따라 결정: ADMIN=ALL, LEARNER=PUBLISHED."
    )
    user_id: ResourceId | None = None
    page: Annotated[int, Field(ge=1)] = 1
    size: Annotated[int, Field(ge=1, le=100)] = 20


class ContentDetailQuery(InputModel):
    view: Literal["learner", "editor"] = "learner"
    user_id: ResourceId | None = None


class VideoQuery(InputModel):
    revision: NonBlankText | None = None
    preview: bool = False
    actor_id: ResourceId | None = None

    @model_validator(mode="after")
    def require_preview_actor(self) -> Self:
        if self.preview and self.actor_id is None:
            raise ValueError("preview=true이면 actor_id가 필요합니다.")
        return self


class ContentFields(InputModel):
    title: Title | None = None
    category_id: ResourceId | None = None
    core_content: NonBlankText | None = None
    source: NonBlankText | None = None
    reviewed_on: date | None = None
    caution_text: NonBlankText | None = None


class ContentCreate(ContentFields):
    tag_ids: list[ResourceId] = Field(default_factory=list)
    caution_enabled: StrictBool = False

    @model_validator(mode="after")
    def validate_caution(self) -> Self:
        if self.caution_enabled and not self.caution_text:
            raise ValueError("주의 표시를 켜려면 caution_text가 필요합니다.")
        return self


class ContentUpdate(ContentFields):
    """전달 필드만 model_dump(exclude_unset=True)로 수정 서비스에 넘긴다."""

    tag_ids: list[ResourceId] = Field(
        default_factory=list, description="생략 시 유지. 전달하면 전체 교체, []는 모두 해제."
    )
    caution_enabled: StrictBool = Field(
        default_factory=lambda: False, description="생략 시 기존 값 유지. null은 허용하지 않음."
    )

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("변경할 필드를 최소 1개 전달해야 합니다.")
        return self


class CategorySummary(ApiModel):
    category_id: ResourceId
    name: Annotated[str, Field(min_length=1, max_length=80)]


class TagSummary(ApiModel):
    tag_id: ResourceId
    name: Annotated[str, Field(min_length=1, max_length=80)]


class CurriculumReference(ApiModel):
    curriculum_id: ResourceId
    title: Title


class ContentSummary(ApiModel):
    content_id: ResourceId
    title: Title | None
    category: CategorySummary | None
    tags: list[TagSummary]
    video_duration: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None
    video_url: str | None
    media_revision: str | None
    view_count: Annotated[int, Field(ge=0)]
    like_count: Annotated[int, Field(ge=0)]
    liked: bool | None
    saved: bool | None
    watch_completed: bool | None
    has_quiz: bool
    status: ContentStatus


class ContentPage(ApiModel):
    items: list[ContentSummary]
    page: Annotated[int, Field(ge=1)]
    size: Annotated[int, Field(ge=1, le=100)]
    total: Annotated[int, Field(ge=0)]
    has_next: bool


class ContentDetail(ApiModel):
    content: ContentSummary
    core_content: str | None
    one_line_summary: str | None
    source: str | None
    reviewed_on: date | None
    caution_enabled: bool
    caution_text: str | None
    related_curriculums: list[CurriculumReference]
    published_at: AwareDatetime | None


class EditableContent(ApiModel):
    detail: ContentDetail
    created_by_user_id: ResourceId
    created_at: AwareDatetime
    updated_at: AwareDatetime
    missing_for_publish: list[str]


class VideoInfo(ApiModel):
    content_id: ResourceId
    video_url: str
    video_duration: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    media_revision: str
    status: ContentStatus
