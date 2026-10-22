from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.contents.models import Content, ContentStatus, VideoAsset
from app.modules.saved_contents.tables import saved_contents


@dataclass(frozen=True)
class SavedCandidate:
    content: Content
    video: VideoAsset | None
    saved_at: datetime


def insert_saved_content(
    session: Session, user_id: int, content_id: int, learning_epoch: int
) -> None:
    """호출자가 권한·공개 상태·현재 세대를 검증하고 잠근 트랜잭션에서 사용한다."""
    session.execute(
        insert(saved_contents)
        .values(user_id=user_id, content_id=content_id, learning_epoch=learning_epoch)
        .on_conflict_do_nothing(
            index_elements=[saved_contents.c.user_id, saved_contents.c.content_id]
        )
    )


def delete_saved_content(session: Session, user_id: int, content_id: int) -> None:
    """호출자의 권한·콘텐츠 존재·세대 검사 및 잠금 뒤 본인 관계만 삭제한다."""
    session.execute(
        delete(saved_contents).where(
            saved_contents.c.user_id == user_id, saved_contents.c.content_id == content_id
        )
    )


def get_saved_content_ids(session: Session, user_id: int, content_ids: list[int]) -> set[int]:
    """대상 접근 검사를 마친 호출자가 개인 저장 상태를 일괄 조회할 때 사용한다."""
    if not content_ids:
        return set()
    return set(
        session.scalars(
            select(saved_contents.c.content_id).where(
                saved_contents.c.user_id == user_id,
                saved_contents.c.content_id.in_(content_ids),
            )
        )
    )


def list_saved_candidates(
    session: Session, user_id: int, *, category_id: int | None = None
) -> list[SavedCandidate]:
    """공개 콘텐츠 후보만 정렬한다. 파일 검사·최종 total·페이징은 수행하지 않는다."""
    statement = (
        select(Content, VideoAsset, saved_contents.c.created_at)
        .select_from(saved_contents)
        .join(Content, Content.content_id == saved_contents.c.content_id)
        .outerjoin(VideoAsset, VideoAsset.video_asset_id == Content.video_asset_id)
        .where(saved_contents.c.user_id == user_id, Content.status == ContentStatus.PUBLISHED)
    )
    if category_id is not None:
        statement = statement.where(Content.category_id == category_id)
    statement = statement.order_by(saved_contents.c.created_at.desc(), Content.content_id)
    # 응답 조립 중 공개 상태·영상 연결이 바뀌지 않게 부모 콘텐츠를 공유 잠근다.
    statement = statement.with_for_update(read=True, of=Content)
    return [SavedCandidate(*row) for row in session.execute(statement)]
