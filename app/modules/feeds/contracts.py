"""파트 1이 제공하는 추천 연결 규격 초안. 파트 2와 합의 후 확정한다.

FeedRanker는 DB·파일·HTTP 접근 없이 입력 후보를 정확히 한 번씩 반환한다.
순서·이유·라벨은 파트 2 소유이며, service.get_feed_ranker에서 연결한다.
후보 입력 순서는 공개 시각 내림차순, 동률이면 콘텐츠 ID 오름차순이다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

RecommendationReason = Literal[
    "LAST_CONTENT", "INTEREST_CATEGORY", "RELATED_TAG", "UNWATCHED", "LATEST"
]


@dataclass(frozen=True)
class FeedCandidate:
    content_id: int
    category_id: int
    tag_ids: frozenset[int]
    published_at: datetime
    # 현재 세대에 실제 시청 기록이 있으면 True. 시청 완료 여부와 다르다.
    watched: bool


@dataclass(frozen=True)
class FeedRankingInput:
    candidates: tuple[FeedCandidate, ...]
    interest_category_ids: frozenset[int]
    # last_content_id가 아니라 last_watched_at이 가장 최신인 기록의 태그.
    # 최신 시청 콘텐츠가 비공개·재생 불가여도 그 기록의 태그를 전달한다.
    recent_watched_tag_ids: frozenset[int]
    # 공개·영상 이용 가능 판정을 통과한 후보 ID 또는 None.
    resume_content_id: int | None


@dataclass(frozen=True)
class RankedFeedItem:
    content_id: int
    recommendation_reason: RecommendationReason
    recommendation_label: str


class FeedRanker(Protocol):
    def __call__(self, context: FeedRankingInput) -> Sequence[RankedFeedItem]: ...
