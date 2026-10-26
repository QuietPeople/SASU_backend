from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.core.types import RecordGeneration
from app.modules.contents.schemas import ContentSummary
from app.modules.feeds.contracts import RecommendationReason


class FeedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: ContentSummary
    recommendation_reason: RecommendationReason
    recommendation_label: Annotated[str, Field(min_length=1, pattern=r"\S")]


class Feed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FeedItem]
    resume_unavailable: bool
    record_generation: RecordGeneration
