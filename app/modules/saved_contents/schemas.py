from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.api.schemas import Page, PageQuery
from app.core.types import PositiveId
from app.modules.contents.schemas import ContentSummary

# 임시 연동 SAV-T05 / 파트 4: 공통 세대 입력 타입 제공 후 참조를 교체한다.
# 기존 API와 동일하게 API 세대 + 1이 DB integer 범위에 들어야 한다.
RecordGeneration = Annotated[int, Field(ge=0, le=2**31 - 2)]


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
