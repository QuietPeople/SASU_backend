from datetime import datetime
from math import isfinite
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.exceptions import ApiError
from app.core.types import PositiveId, RecordGeneration


class WatchVisitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visit_id: UUID
    media_revision: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
    ]
    actual_played_seconds: Annotated[float, Field(strict=True)]
    watched_segments: list[list[Annotated[float, Field(strict=True)]]]
    context: Literal["FEED", "SEARCH", "CURRICULUM", "LIBRARY", "REVIEW"]

    @model_validator(mode="after")
    def validate_report(self) -> "WatchVisitBody":
        valid = (
            isfinite(self.actual_played_seconds)
            and 0 < self.actual_played_seconds <= 99_999_999_999.999
            and 1 <= len(self.watched_segments) <= 4000
            and all(
                len(r) == 2 and all(isfinite(v) for v in r) and 0 <= r[0] < r[1]
                for r in self.watched_segments
            )
        )
        if not valid:
            raise ApiError(
                422, "INVALID_WATCH_REPORT", "유효한 재생 시간과 시청 구간을 전달해 주세요."
            )
        return self


class WatchVisitResult(BaseModel):
    user_id: PositiveId
    content_id: PositiveId
    visit_id: UUID
    view_counted: bool
    newly_view_counted: bool
    watch_completed: bool
    visit_watch_percent: float
    max_watch_percent: float
    feed_completion_eligible: bool
    view_count: int
    first_played_at: datetime
    last_watched_at: datetime
    completed_at: datetime | None
    record_generation: RecordGeneration
