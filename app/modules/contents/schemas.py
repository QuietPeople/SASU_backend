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
ContentStatus = Literal["DRAFT", "PUBLISHED", "PRIVATE"]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InputModel(ApiModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class ContentListQuery(InputModel, PageQuery):
    missing: Literal["video", "learning_material", "either"] | None = None
    q: Annotated[str, Field(max_length=200)] | None = None
    category_id: ResourceId | None = None
    status: Literal["DRAFT", "PUBLISHED", "PRIVATE", "ALL"] | None = Field(
        default=None, description="생략 시 역할에 따라 결정: ADMIN=ALL, LEARNER=PUBLISHED."
    )
    user_id: ResourceId | None = None


class ContentDetailQuery(InputModel, ViewQuery):
    user_id: ResourceId | None = None


class ThumbnailQuery(InputModel):
    preview: bool = False
    actor_id: ResourceId | None = None

    @model_validator(mode="after")
    def require_preview_actor(self) -> Self:
        if self.preview and self.actor_id is None:
            raise ValueError("preview=true이면 actor_id가 필요합니다.")
        return self


class VideoQuery(ThumbnailQuery):
    revision: NonBlankText | None = None


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
    """편집 조회 시각을 전달하면 오래된 저장을 거절한다."""

    expected_updated_at: AwareDatetime

    tag_ids: list[StrictResourceId] = Field(
        default_factory=list, description="생략 시 유지. 전달하면 전체 교체, []는 모두 해제."
    )
    caution_enabled: StrictBool = Field(
        default_factory=lambda: False, description="생략 시 기존 값 유지. null은 허용하지 않음."
    )

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        if not self.model_fields_set - {"expected_updated_at"}:
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
    thumbnail_url: str | None = None


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


class ContentVersion(InputModel):
    expected_updated_at: AwareDatetime


class ContentDelete(ContentVersion):
    confirm: StrictBool

    @field_validator("confirm")
    @classmethod
    def require_confirmation(cls, value: bool) -> bool:
        if not value:
            raise ValueError("영구 삭제에는 confirm=true가 필요합니다.")
        return value


class ContentDeleted(ApiModel):
    content_id: ResourceId
    file_cleanup_pending: bool


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
    max_long_edge_px: int = Field(description="입력 영상의 긴 변 상한(포함). 기본 3840px.")
    target_long_edge_px: int = Field(
        description="자동 축소 후 저장할 긴 변 목표. 작은 영상은 확대하지 않음."
    )
    accept: str
    formats: list[str]
