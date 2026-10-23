from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.types import PositiveId, RecordGeneration


class UserSettings(BaseModel):
    user_id: PositiveId
    interest_category_ids: list[PositiveId]
    interest_guide_completed: bool
    review_interval: int
    record_generation: RecordGeneration


class PatchSettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interest_category_ids: list[Annotated[PositiveId, Field(strict=True)]] | None = None
    interest_guide_completed: Annotated[bool, Field(strict=True)] | None = None
    review_interval: Annotated[int, Field(strict=True, ge=1, le=20)] | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> "PatchSettingsBody":
        if not self.model_fields_set:
            raise ValueError("최소 한 개의 설정을 전달해 주세요.")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("설정은 null로 비울 수 없습니다.")
        if self.interest_category_ids is not None:
            if self.interest_guide_completed is False:
                raise ValueError("관심 목록 변경과 안내 미완료를 함께 요청할 수 없습니다.")
            self.interest_category_ids = sorted(set(self.interest_category_ids))
        return self


class FeedPosition(BaseModel):
    user_id: PositiveId
    last_content_id: PositiveId | None
    resume_available: bool
    record_generation: RecordGeneration


class UpdateFeedPositionBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    last_content_id: PositiveId
