from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import case, delete, func, literal, or_, select
from sqlalchemy.orm import Session

from app.modules.categories.models import Category
from app.modules.contents import read_tables as reads
from app.modules.contents.models import Content, ContentTag, VideoAsset
from app.modules.contents.schemas import ContentListQuery
from app.modules.tags.models import Tag


def get_category(session: Session, category_id: int) -> Category | None:
    return session.get(Category, category_id)


def get_tags(session: Session, tag_ids: list[int]) -> list[Tag]:
    if not tag_ids:
        return []
    return list(session.scalars(select(Tag).where(Tag.tag_id.in_(tag_ids)).order_by(Tag.tag_id)))


def insert_content(session: Session, content: Content, tag_ids: list[int]) -> None:
    session.add(content)
    session.flush()
    session.add_all(ContentTag(content_id=content.content_id, tag_id=tag_id) for tag_id in tag_ids)
    session.flush()


def get_content_for_update(session: Session, content_id: int) -> Content | None:
    return session.scalar(select(Content).where(Content.content_id == content_id).with_for_update())


def attach_video(session: Session, content: Content, asset: VideoAsset) -> None:
    session.add(asset)
    session.flush()
    content.video_asset_id = asset.video_asset_id
    content.updated_at = datetime.now(UTC)
    session.flush()


@dataclass
class Presentation:
    content: Content
    category: Category | None = None
    video: VideoAsset | None = None
    tags: list[Tag] = field(default_factory=list)
    view_count: int = 0
    like_count: int = 0
    liked: bool | None = None
    saved: bool | None = None
    watch_completed: bool | None = None
    has_quiz: bool = False


def get_content(
    session: Session, content_id: int, *, lock_for_video: bool = False
) -> Content | None:
    statement = select(Content).where(Content.content_id == content_id)
    if lock_for_video:
        statement = statement.with_for_update(read=True)
    return session.scalar(statement)


def list_contents(
    session: Session, query: ContentListQuery, status: str
) -> tuple[list[Content], int]:
    statement = select(Content)
    if status != "ALL":
        statement = statement.where(Content.status == status)
    if query.category_id is not None:
        statement = statement.where(Content.category_id == query.category_id)
    ordering = []
    if query.q:
        title_match = Content.title.icontains(query.q, autoescape=True)
        tag_match = (
            select(ContentTag.content_id)
            .join(Tag, Tag.tag_id == ContentTag.tag_id)
            .where(
                ContentTag.content_id == Content.content_id,
                Tag.name.icontains(query.q, autoescape=True),
            )
            .correlate(Content)
            .exists()
        )
        core_match = Content.core_content.icontains(query.q, autoescape=True)
        statement = statement.where(or_(title_match, tag_match, core_match))
        ordering.append(case((title_match, 0), (tag_match, 1), else_=2))
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    statement = (
        statement.order_by(*ordering, Content.published_at.desc().nulls_last(), Content.content_id)
        .offset((query.page - 1) * query.size)
        .limit(query.size)
    )
    return list(session.scalars(statement)), total


def load_presentations(
    session: Session, contents: list[Content], user_id: int | None = None
) -> list[Presentation]:
    if not contents:
        return []
    ids = [content.content_id for content in contents]
    quiz_exists = (
        select(reads.quizzes.c.content_id)
        .where(
            reads.quizzes.c.content_id == Content.content_id,
            reads.quizzes.c.current_version_id.is_not(None),
        )
        .correlate(Content)
        .exists()
    )

    def personal(table, *conditions):
        if user_id is None:
            return literal(None)
        return (
            select(table.c.content_id)
            .where(
                table.c.content_id == Content.content_id, table.c.user_id == user_id, *conditions
            )
            .correlate(Content)
            .exists()
        )

    rows = session.execute(
        select(
            Content.content_id,
            Category,
            VideoAsset,
            func.coalesce(reads.content_metrics.c.view_count, 0),
            func.coalesce(reads.content_metrics.c.like_count, 0),
            quiz_exists,
            personal(reads.content_likes),
            personal(reads.saved_contents),
            personal(reads.watch_records, reads.watch_records.c.completed_at.is_not(None)),
        )
        .select_from(Content)
        .outerjoin(Category, Category.category_id == Content.category_id)
        .outerjoin(VideoAsset, VideoAsset.video_asset_id == Content.video_asset_id)
        .outerjoin(reads.content_metrics, reads.content_metrics.c.content_id == Content.content_id)
        .where(Content.content_id.in_(ids))
    )
    by_id = {content.content_id: Presentation(content) for content in contents}
    for content_id, category, video, views, likes, quiz, liked, saved, completed in rows:
        item = by_id[content_id]
        item.category, item.video = category, video
        item.view_count, item.like_count, item.has_quiz = views, likes, quiz
        item.liked, item.saved, item.watch_completed = liked, saved, completed
    for content_id, tag in session.execute(
        select(ContentTag.content_id, Tag)
        .join(Tag, Tag.tag_id == ContentTag.tag_id)
        .where(ContentTag.content_id.in_(ids))
        .order_by(ContentTag.content_id, Tag.tag_id)
    ):
        by_id[content_id].tags.append(tag)
    return [by_id[content_id] for content_id in ids]


def related_curriculums(session: Session, content_id: int) -> list[dict]:
    rows = session.execute(
        select(reads.curricula.c.curriculum_id, reads.curricula.c.title)
        .join(
            reads.curriculum_items,
            reads.curriculum_items.c.curriculum_id == reads.curricula.c.curriculum_id,
        )
        .where(reads.curriculum_items.c.content_id == content_id)
        .order_by(reads.curricula.c.curriculum_id)
    )
    return [dict(row._mapping) for row in rows]


def replace_tags(session: Session, content_id: int, tag_ids: list[int]) -> None:
    session.execute(delete(ContentTag).where(ContentTag.content_id == content_id))
    session.add_all(ContentTag(content_id=content_id, tag_id=tag_id) for tag_id in tag_ids)
