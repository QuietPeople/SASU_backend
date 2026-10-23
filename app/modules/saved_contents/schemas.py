from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.api.schemas import Page, PageQuery
from app.core.types import PositiveId
from app.modules.contents.schemas import ContentSummary


class SaveState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_id: PositiveId
    saved: bool


class SavedContentsQuery(PageQuery):
    category_id: PositiveId | None = None


class SavedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: ContentSummary
    saved_at: AwareDatetime


class SavedContentsPage(Page[SavedItem]):
    model_config = ConfigDict(extra="forbid")

    page: Annotated[int, Field(ge=1)]
    size: Annotated[int, Field(ge=1, le=100)]
    total: Annotated[int, Field(ge=0)]
