from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.core.types import PositiveId

# API 세대에 1을 더한 DB learning_epoch가 PostgreSQL integer 범위에 들어야 한다.
RecordGeneration = Annotated[int, Field(ge=0, le=2**31 - 2)]


class LikeState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_id: PositiveId
    liked: bool
    like_count: Annotated[int, Field(ge=0)]
