from datetime import date
from re import fullmatch
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from app.api.schemas import Page, PageQuery, ViewQuery
from app.core.types import PositiveId as ResourceId
from app.modules.categories.schemas import CategoryRead
from app.modules.tags.schemas import TagRead

StrictResourceId = Annotated[ResourceId, Field(strict=True)]
NonBlankText = Annotated[str, Field(min_length=1)]
Title = Annotated[str, Field(min_length=1, max_length=200)]
ContentStatus = Literal["DRAFT", "PUBLISHED"]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InputModel(ApiModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class ContentListQuery(InputModel, PageQuery):
    q: Annotated[str, Field(max_length=200)] | None = None
    category_id: ResourceId | None = None
    status: Literal["DRAFT", "PUBLISHED", "ALL"] | None = Field(
        default=None, description="생략 시 역할에 따라 결정: ADMIN=ALL, LEARNER=PUBLISHED."
    )
    user_id: ResourceId | None = None


class ContentDetailQuery(InputModel, ViewQuery):
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
    category_id: StrictResourceId | None = None
    core_content: NonBlankText | None = None
    source: NonBlankText | None = None
    reviewed_on: date | None = None
    caution_text: NonBlankText | None = None

    @field_validator("reviewed_on", mode="before")
    @classmethod
    def validate_reviewed_on(cls, value):
        if value is None or type(value) is date:
            return value
        if (
            not isinstance(value, str)
            or fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value.strip()) is None
        ):
            raise ValueError("검토일은 YYYY-MM-DD 형식이어야 합니다.")
        return date.fromisoformat(value.strip())


class ContentCreate(ContentFields):
    tag_ids: list[StrictResourceId] = Field(default_factory=list)
    caution_enabled: StrictBool = False

    @model_validator(mode="after")
    def validate_caution(self) -> Self:
        if self.caution_enabled and not self.caution_text:
            raise ValueError("주의 표시를 켜려면 caution_text가 필요합니다.")
        return self


class ContentUpdate(ContentFields):
    """전달 필드만 model_dump(exclude_unset=True)로 수정 서비스에 넘긴다."""

    tag_ids: list[StrictResourceId] = Field(
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


class CategorySummary(CategoryRead):
    model_config = ConfigDict(extra="forbid", from_attributes=False)


class TagSummary(TagRead):
    model_config = ConfigDict(extra="forbid", from_attributes=False)


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


class ContentPage(Page[ContentSummary]):
    model_config = ConfigDict(extra="forbid")

    page: Annotated[int, Field(ge=1)]
    size: Annotated[int, Field(ge=1, le=100)]
    total: Annotated[int, Field(ge=0)]


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


class VideoPolicyOut(ApiModel):
    """영상 업로드 허용 조건(데이터 처리 정책). 화면 안내용."""

    max_bytes: int
    min_duration_sec: float
    max_duration_sec: float
    max_long_edge_px: int
    accept: str
    formats: list[str]
