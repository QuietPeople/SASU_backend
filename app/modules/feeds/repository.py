"""피드 전용 읽기 쿼리. 공식 모델·테이블과 콘텐츠 일괄 조회를 재사용한다."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.contents.models import Content, ContentStatus, ContentTag
from app.modules.contents.repository import Presentation, load_presentations
from app.modules.users.settings_tables import user_interests
from app.modules.watch_records.tables import watch_records


def published_presentations(session: Session, user_id: int) -> list[Presentation]:
    # 검색 API의 페이지 제한을 적용하지 않는다. 설정 SHARE 잠금 뒤 콘텐츠를
    # 잠가 응답 작성 중 비공개 전환·영상 교체와 섞이지 않게 한다.
    contents = list(
        session.scalars(
            select(Content)
            .where(Content.status == ContentStatus.PUBLISHED)
            .order_by(Content.published_at.desc(), Content.content_id)
            .with_for_update(read=True)
        )
    )
    return load_presentations(session, contents, user_id)


def interest_category_ids(session: Session, user_id: int) -> frozenset[int]:
    return frozenset(
        session.scalars(
            select(user_interests.c.category_id).where(user_interests.c.user_id == user_id)
        )
    )


def watch_context(
    session: Session, user_id: int, epoch: int
) -> tuple[frozenset[int], frozenset[int]]:
    watched_ids = list(
        session.scalars(
            select(watch_records.c.content_id)
            .where(watch_records.c.user_id == user_id, watch_records.c.learning_epoch == epoch)
            .order_by(watch_records.c.last_watched_at.desc(), watch_records.c.content_id)
        )
    )
    latest_tags = (
        frozenset(
            session.scalars(
                select(ContentTag.tag_id).where(ContentTag.content_id == watched_ids[0])
            )
        )
        if watched_ids
        else frozenset()
    )
    return frozenset(watched_ids), latest_tags
