from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.types import PositiveId

RecordGeneration = Annotated[int, Field(ge=0, le=2**31 - 2)]
OnboardingStatus = Literal["PENDING", "DONE", "SKIPPED"]
FeedContext = Literal["FEED", "SEARCH", "SAVED", "CURRICULUM", "REVIEW"]


class CategoryRef(BaseModel):
    category_id: int
    name: str


class UserSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    onboarding_status: OnboardingStatus
    review_interval: Annotated[int, Field(ge=1, le=20)]
    interests: list[CategoryRef]
    record_generation: RecordGeneration


class PatchSettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    onboarding_status: OnboardingStatus | None = None
    review_interval: Annotated[int, Field(ge=1, le=20)] | None = None
    interest_category_ids: list[PositiveId] | None = None


class FeedPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_content_id: PositiveId | None
    resume_unavailable: bool


class UpdateFeedPositionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_id: PositiveId
    context: FeedContext
