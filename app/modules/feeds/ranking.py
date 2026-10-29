"""CNT-01 규칙 추천. 조회·저장 없이 파트 1의 후보를 정렬한다."""

from app.modules.feeds.contracts import FeedRankingInput, RankedFeedItem, RecommendationReason

_LABELS: dict[RecommendationReason, str] = {
    "LAST_CONTENT": "마지막으로 보던 영상",
    "INTEREST_CATEGORY": "관심 카테고리의 영상",
    "RELATED_TAG": "최근 시청한 영상과 관련된 태그의 영상",
    "UNWATCHED": "아직 시청하지 않은 영상",
    "LATEST": "최근 공개된 영상",
}


def rank_feed(context: FeedRankingInput) -> tuple[RankedFeedItem, ...]:
    """재개를 선두에, 나머지는 관심 > 태그 > 미시청의 사전식 순서로 반환.

    동점은 공개 시각 내림차순, ID 오름차순이다. 입력은 변경하지 않는다.
    published_at은 파트 1에서 전달하는 DB의 timezone-aware datetime이다.
    중복 ID는 조회 계약 위반으로 거절하여 임의로 서로 다른 후보를 합치지 않는다.
    재개 ID가 후보에 없으면 삽입하지 않는다(재개 불가 응답은 파트 1 담당).
    """
    candidates = context.candidates
    if len({item.content_id for item in candidates}) != len(candidates):
        raise ValueError("Feed candidates must have unique content IDs")

    cold_start = not (
        context.interest_category_ids
        or context.recent_watched_tag_ids
        or any(item.watched for item in candidates)
    )
    # 안정 정렬로 datetime을 숫자로 변환하지 않고 정확한 시각 비교를 유지한다.
    ordered = sorted(candidates, key=lambda item: item.content_id)
    ordered.sort(key=lambda item: item.published_at, reverse=True)
    ordered.sort(
        key=lambda item: (
            item.content_id == context.resume_content_id,
            item.category_id in context.interest_category_ids,
            bool(item.tag_ids & context.recent_watched_tag_ids),
            not item.watched,
        ),
        reverse=True,
    )
    result = []
    for item in ordered:
        reason: RecommendationReason
        if item.content_id == context.resume_content_id:
            reason = "LAST_CONTENT"
        elif item.category_id in context.interest_category_ids:
            reason = "INTEREST_CATEGORY"
        elif item.tag_ids & context.recent_watched_tag_ids:
            reason = "RELATED_TAG"
        elif not item.watched and not cold_start:
            reason = "UNWATCHED"
        else:
            reason = "LATEST"
        result.append(RankedFeedItem(item.content_id, reason, _LABELS[reason]))
    return tuple(result)
