from app.modules.contents.schemas import ContentSummary
from app.modules.contents.urls import build_video_url


def build_summary(row, actor_id: int, *, preview: bool = False) -> ContentSummary:
    """권한 확인된 조회 결과를 공통 콘텐츠 응답으로 조립한다. 조회·필터링은 호출자 책임이다."""
    revision = str(row["video_asset_id"]) if row["video_asset_id"] else None
    return ContentSummary(
        content_id=row["content_id"],
        title=row["title"],
        category={"category_id": row["category_id"], "name": row["category_name"]}
        if row["category_id"] is not None
        else None,
        tags=row["tags"],
        video_duration=row["duration_seconds"],
        video_url=build_video_url(
            row["content_id"], revision, preview_actor_id=actor_id if preview else None
        )
        if revision
        else None,
        media_revision=revision,
        view_count=row["view_count"],
        like_count=row["like_count"],
        liked=row["liked"],
        saved=row["saved"],
        watch_completed=row["watch_completed"],
        has_quiz=row["has_quiz"],
        status=row["status"],
    )
