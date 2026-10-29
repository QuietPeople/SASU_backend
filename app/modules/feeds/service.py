from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.integrations.storage import LocalVideoStorage
from app.modules.contents.service import build_content_summary, is_video_available
from app.modules.feeds import repository
from app.modules.feeds.contracts import FeedCandidate, FeedRanker, FeedRankingInput
from app.modules.feeds.ranking import rank_feed
from app.modules.feeds.schemas import Feed, FeedItem
from app.modules.users.service import require_learner
from app.modules.users.settings_repository import get_feed_position
from app.modules.users.settings_service import current_epoch


def get_feed_ranker() -> FeedRanker:
    return rank_feed


def get_feed(session: Session, actor_id: int, user_id: int, ranker: FeedRanker) -> Feed:
    with session.begin_nested() if session.in_transaction() else session.begin():
        require_learner(session, actor_id, user_id)
        # 초기화·설정·학습 기록 변경과 같은 잠금 기준을 사용한다. 세대 요청 헤더는 없다.
        epoch = current_epoch(session, user_id, write=False)
        storage = LocalVideoStorage(get_settings().video_storage_root)
        presentations = [
            item
            for item in repository.published_presentations(session, user_id)
            if is_video_available(item.video, storage)
        ]
        by_id = {item.content.content_id: item for item in presentations}
        watched_ids, recent_tags = repository.watch_context(session, user_id, epoch)
        last_content_id = get_feed_position(session, user_id)["last_content_id"]
        resume_id = last_content_id if last_content_id in by_id else None
        candidates = []
        for item in presentations:
            content = item.content
            # PUBLISHED 필수 필드는 기존 DB 제약조건이 보장한다.
            assert content.category_id is not None and content.published_at is not None
            candidates.append(
                FeedCandidate(
                    content_id=content.content_id,
                    category_id=content.category_id,
                    tag_ids=frozenset(tag.tag_id for tag in item.tags),
                    published_at=content.published_at,
                    watched=content.content_id in watched_ids,
                )
            )
        context = FeedRankingInput(
            candidates=tuple(candidates),
            interest_category_ids=repository.interest_category_ids(session, user_id),
            recent_watched_tag_ids=recent_tags,
            resume_content_id=resume_id,
        )
        ranked = tuple(ranker(context))
        ranked_ids = [item.content_id for item in ranked]
        if len(ranked_ids) != len(by_id) or set(ranked_ids) != set(by_id):
            raise ApiError(500, "INTERNAL_ERROR", "피드 추천 결과를 확인할 수 없습니다.")
        # SHARE 잠금이 유지되는 동안 개인 상태를 포함한 응답까지 완성한다.
        return Feed(
            items=[
                FeedItem(
                    content=build_content_summary(by_id[item.content_id], actor_id),
                    recommendation_reason=item.recommendation_reason,
                    recommendation_label=item.recommendation_label,
                )
                for item in ranked
            ],
            resume_unavailable=last_content_id is not None and resume_id is None,
            record_generation=epoch - 1,
        )
