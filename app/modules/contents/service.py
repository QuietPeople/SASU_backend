import re
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.integrations.storage import LocalVideoStorage
from app.modules.contents import repository
from app.modules.contents.models import Content, ContentStatus, VideoAsset
from app.modules.contents.presentation import build_summary
from app.modules.contents.schemas import (
    ContentCreate,
    ContentDetail,
    ContentDetailQuery,
    ContentListQuery,
    ContentPage,
    ContentSummary,
    ContentUpdate,
    EditableContent,
)
from app.modules.users.models import UserRole
from app.modules.users.repository import get_user
from app.modules.users.service import get_actor, require_admin
from app.modules.videos import availability


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _reader(session: Session, actor_id: int, user_id: int | None):
    actor = get_actor(session, actor_id)
    if actor.role == UserRole.LEARNER:
        if user_id is not None and user_id != actor_id:
            raise ApiError(404, "USER_NOT_FOUND", "조회 가능한 학습자가 없습니다.")
        return actor, actor_id
    if user_id is not None:
        target = get_user(session, user_id)
        if target is None or target.role != UserRole.LEARNER:
            raise ApiError(404, "USER_NOT_FOUND", "조회 가능한 학습자가 없습니다.")
    return actor, user_id


def build_content_summary(item: repository.Presentation, actor_id: int) -> ContentSummary:
    content, video, category = item.content, item.video, item.category
    return build_summary(
        {
            "content_id": content.content_id,
            "title": content.title,
            "category_id": category.category_id if category else None,
            "category_name": category.name if category else None,
            "tags": [{"tag_id": tag.tag_id, "name": tag.name} for tag in item.tags],
            "video_asset_id": video.video_asset_id if video else None,
            "duration_seconds": video.duration_seconds if video else None,
            "view_count": item.view_count,
            "like_count": item.like_count,
            "liked": item.liked,
            "saved": item.saved,
            "watch_completed": item.watch_completed,
            "has_quiz": item.has_quiz,
            "status": content.status,
        },
        actor_id,
        preview=content.status == ContentStatus.DRAFT,
    )


def _detail(item: repository.Presentation, actor_id: int, related: list[dict]) -> ContentDetail:
    content = item.content
    return ContentDetail(
        content=build_content_summary(item, actor_id),
        core_content=content.core_content,
        one_line_summary=re.split(r"(?<=[.!?。！？])\s+|\n", content.core_content, maxsplit=1)[0]
        if content.core_content
        else None,
        source=content.source,
        reviewed_on=content.reviewed_on,
        caution_enabled=content.caution_enabled,
        caution_text=content.caution_text,
        related_curriculums=related,
        published_at=_utc(content.published_at) if content.published_at else None,
    )


def is_video_available(video: VideoAsset | None, storage: LocalVideoStorage) -> bool:
    """콘텐츠 ORM 자산을 영상 담당 검사에 전달한다."""
    return video is not None and availability.is_video_available(
        video.storage_path,
        size_bytes=video.size_bytes,
        mime_type=video.mime_type,
        duration_seconds=video.duration_seconds,
        storage=storage,
    )


def _missing(item: repository.Presentation, storage: LocalVideoStorage | None) -> list[str]:
    content, video = item.content, item.video
    video_valid = video is not None if storage is None else is_video_available(video, storage)
    fields = {
        "video": video_valid,
        "title": content.title,
        "category_id": content.category_id,
        "tag_ids": item.tags,
        "core_content": content.core_content,
        "source": content.source,
        "reviewed_on": content.reviewed_on,
    }
    return [name for name, value in fields.items() if not value]


def _validate_publish(item: repository.Presentation, storage: LocalVideoStorage) -> None:
    missing = _missing(item, storage)
    if missing:
        raise ApiError(
            422,
            "PUBLISH_REQUIREMENTS_MISSING",
            "공개 필수 정보를 확인해 주세요.",
            fields=[{"field": name, "reason": "required_for_publish"} for name in missing],
        )


def _validate_caution(content: Content) -> None:
    if content.caution_enabled and not content.caution_text:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "주의 표시를 켜려면 주의 문구가 필요합니다.",
            fields=[{"field": "caution_text", "reason": "required_when_caution_enabled"}],
        )


def _editable(
    item: repository.Presentation,
    actor_id: int,
    related: list[dict],
    storage: LocalVideoStorage | None = None,
) -> EditableContent:
    content = item.content
    return EditableContent(
        detail=_detail(item, actor_id, related),
        created_by_user_id=content.created_by_user_id,
        created_at=_utc(content.created_at),
        updated_at=_utc(content.updated_at),
        missing_for_publish=_missing(item, storage),
    )


def _category(session: Session, category_id: int | None):
    category = repository.get_category(session, category_id) if category_id is not None else None
    if category_id is not None and category is None:
        raise ApiError(404, "CATEGORY_NOT_FOUND", "지정한 카테고리가 없습니다.")
    return category


def _tags(session: Session, tag_ids: list[int]):
    tags = repository.get_tags(session, list(dict.fromkeys(tag_ids)))
    if len(tags) != len(set(tag_ids)):
        raise ApiError(404, "TAG_NOT_FOUND", "지정한 태그가 없습니다.")
    return tags


def create_content(session: Session, actor_id: int, data: ContentCreate) -> EditableContent:
    try:
        with session.begin():
            require_admin(session, actor_id)
            category, tags = _category(session, data.category_id), _tags(session, data.tag_ids)
            content = Content(
                **data.model_dump(exclude={"tag_ids"}),
                created_by_user_id=actor_id,
                status=ContentStatus.DRAFT,
            )
            repository.insert_content(session, content, [tag.tag_id for tag in tags])
            result = _editable(
                repository.Presentation(content, category=category, tags=tags), actor_id, []
            )
        return result
    except SQLAlchemyError as exc:
        raise ApiError(500, "INTERNAL_ERROR", "콘텐츠 저장에 실패했습니다.") from exc


def list_contents(session: Session, actor_id: int, query: ContentListQuery) -> ContentPage:
    try:
        with session.begin():
            actor, target_id = _reader(session, actor_id, query.user_id)
            status = query.status or ("ALL" if actor.role == UserRole.ADMIN else "PUBLISHED")
            if actor.role != UserRole.ADMIN and status != "PUBLISHED":
                raise ApiError(403, "EDITOR_VIEW_REQUIRED", "임시저장 조회는 관리자만 가능합니다.")
            _category(session, query.category_id)
            contents, total = repository.list_contents(session, query, status)
            items = repository.load_presentations(session, contents, target_id)
            return ContentPage(
                items=[build_content_summary(item, actor_id) for item in items],
                page=query.page,
                size=query.size,
                total=total,
                has_next=query.page * query.size < total,
            )
    except SQLAlchemyError as exc:
        raise ApiError(500, "INTERNAL_ERROR", "콘텐츠 목록 조회에 실패했습니다.") from exc


def get_content(
    session: Session,
    actor_id: int,
    content_id: int,
    query: ContentDetailQuery,
    storage: LocalVideoStorage,
) -> ContentDetail | EditableContent:
    try:
        with session.begin():
            actor, target_id = _reader(session, actor_id, query.user_id)
            if query.view == "editor" and actor.role != UserRole.ADMIN:
                raise ApiError(403, "EDITOR_VIEW_REQUIRED", "편집 조회는 관리자만 가능합니다.")
            content = repository.get_content(session, content_id)
            if content is None or (
                query.view == "learner" and content.status != ContentStatus.PUBLISHED
            ):
                raise ApiError(404, "CONTENT_NOT_FOUND", "조회 가능한 콘텐츠가 없습니다.")
            item = repository.load_presentations(session, [content], target_id)[0]
            related = repository.related_curriculums(session, content_id)
            if query.view == "editor":
                return _editable(item, actor_id, related, storage)
            return _detail(item, actor_id, related)
    except SQLAlchemyError as exc:
        raise ApiError(500, "INTERNAL_ERROR", "콘텐츠 상세 조회에 실패했습니다.") from exc


def update_content(
    session: Session,
    actor_id: int,
    content_id: int,
    data: ContentUpdate,
    storage: LocalVideoStorage,
) -> EditableContent:
    try:
        with session.begin(), session.no_autoflush:
            require_admin(session, actor_id)
            content = repository.get_content_for_update(session, content_id)
            if content is None:
                raise ApiError(404, "CONTENT_NOT_FOUND", "콘텐츠가 없습니다.")
            item = repository.load_presentations(session, [content])[0]
            changes = data.model_dump(exclude_unset=True)
            if "category_id" in changes:
                item.category = _category(session, changes["category_id"])
            tag_ids = changes.pop("tag_ids", None)
            if tag_ids is not None:
                item.tags = _tags(session, tag_ids)
            for name, value in changes.items():
                setattr(content, name, value)
            _validate_caution(content)
            if content.status == ContentStatus.PUBLISHED:
                _validate_publish(item, storage)
            if tag_ids is not None:
                repository.replace_tags(session, content_id, [tag.tag_id for tag in item.tags])
            content.updated_at = datetime.now(UTC)
            session.flush()
            result = _editable(
                item, actor_id, repository.related_curriculums(session, content_id), storage
            )
        return result
    except SQLAlchemyError as exc:
        raise ApiError(500, "INTERNAL_ERROR", "콘텐츠 수정에 실패했습니다.") from exc


def publish_content(
    session: Session,
    actor_id: int,
    content_id: int,
    storage: LocalVideoStorage,
) -> EditableContent:
    try:
        with session.begin():
            require_admin(session, actor_id)
            content = repository.get_content_for_update(session, content_id)
            if content is None:
                raise ApiError(404, "CONTENT_NOT_FOUND", "콘텐츠가 없습니다.")
            item = repository.load_presentations(session, [content])[0]
            _validate_caution(content)
            _validate_publish(item, storage)
            if content.status != ContentStatus.PUBLISHED:
                content.status = ContentStatus.PUBLISHED
                content.published_at = datetime.now(UTC)
                content.updated_at = content.published_at
                session.flush()
            result = _editable(
                item, actor_id, repository.related_curriculums(session, content_id), storage
            )
        return result
    except SQLAlchemyError as exc:
        raise ApiError(500, "INTERNAL_ERROR", "콘텐츠 공개 처리에 실패했습니다.") from exc
