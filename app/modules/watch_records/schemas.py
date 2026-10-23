from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

WatchContext = Literal["FEED", "SEARCH", "SAVED", "CURRICULUM", "REVIEW"]

VisitId = Annotated[UUID, Field(description="클라이언트가 생성한 방문 UUID")]


class WatchVisitBody(BaseModel):
    video_asset_id: UUID
    context: WatchContext
    elapsed_seconds: float = Field(ge=0, description="이번 방문의 실제 재생 시간(초). 일시정지·로딩·seek 제외.")
    watched_ranges: list[list[float]] = Field(
        default_factory=list,
        description="이번 방문에 실제로 본 구간. 각 항목은 [시작초, 끝초].",
    )
    sequence: int = Field(ge=0, description="수신 순번. 이전 순번 이하 요청은 무시.")

    @field_validator("watched_ranges")
    @classmethod
    def validate_ranges(cls, v: list[list[float]]) -> list[list[float]]:
        for rng in v:
            if len(rng) != 2:
                raise ValueError("구간은 [시작, 끝] 형식이어야 합니다.")
            if rng[1] <= rng[0]:
                raise ValueError("구간의 끝이 시작보다 커야 합니다.")
            if rng[0] < 0:
                raise ValueError("구간의 시작은 0 이상이어야 합니다.")
        return v


class WatchVisitResult(BaseModel):
    view_counted: bool = Field(description="이번 요청으로 3초 조회가 인정됐는지.")
    completed: bool = Field(description="이 콘텐츠의 시청 완료 여부(이전 방문 포함).")
    coverage: float = Field(description="이번 방문의 겹침 제거 구간 비율(0~1).")
    video_changed: bool = Field(description="방문 당시 자산과 현재 콘텐츠 자산이 다른지.")
