"""관리자 비공개 전환 및 콘텐츠 전체 영구 삭제."""

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ApiError, check_edit_version
from app.integrations.storage import LocalImageStorage, LocalVideoStorage
from app.modules.contents import lifecycle_repository, repository, service
from app.modules.contents.models import ContentStatus
from app.modules.contents.schemas import (
    ContentDelete,
    ContentDeleted,
    ContentVersion,
    EditableContent,
)
from app.modules.users.service import require_admin

logger = logging.getLogger(__name__)


def unpublish_content(
    session: Session, actor_id: int, content_id: int, body: ContentVersion
) -> EditableContent:
    try:
        with session.begin():
            require_admin(session, actor_id)
            content = repository.get_content_for_update(session, content_id)
            if content is None:
                raise ApiError(404, "CONTENT_NOT_FOUND", "콘텐츠가 없습니다.")
            check_edit_version(body.expected_updated_at, service._utc(content.updated_at))
            if content.status == ContentStatus.DRAFT:
                raise ApiError(
                    409, "CONTENT_NOT_PUBLISHED", "임시저장 콘텐츠는 공개 이력이 없습니다."
                )
            if content.status != ContentStatus.PRIVATE:
                content.status = ContentStatus.PRIVATE
                content.updated_at = datetime.now(UTC)
                session.flush()
            item = repository.load_presentations(session, [content])[0]
            return service._editable(
                item,
                actor_id,
                repository.related_curriculums(session, content_id),
                LocalVideoStorage(get_settings().video_storage_root),
            )
    except SQLAlchemyError as exc:
        raise ApiError(500, "INTERNAL_ERROR", "콘텐츠 비공개 전환에 실패했습니다.") from exc


def delete_content(
    session: Session, actor_id: int, content_id: int, body: ContentDelete
) -> ContentDeleted:
    try:
        with session.begin():
            require_admin(session, actor_id)
            lifecycle_repository.lock_deletion(session)
            content = repository.get_content_for_update(session, content_id)
            if content is None:
                raise ApiError(404, "CONTENT_NOT_FOUND", "콘텐츠가 없습니다.")
            check_edit_version(body.expected_updated_at, service._utc(content.updated_at))
            files = lifecycle_repository.delete_owned_rows(session, content)
    except SQLAlchemyError as exc:
        raise ApiError(500, "INTERNAL_ERROR", "콘텐츠 삭제에 실패했습니다.") from exc

    # 커밋 전 파일을 지우지 않아 DB 실패 시 기존 영상을 그대로 유지한다.
    # 새 작업 테이블을 두지 않으므로 정리 실패는 응답과 운영 로그에 명확히 남긴다.
    settings = get_settings()
    stores = {
        "video": LocalVideoStorage(settings.video_storage_root),
        "image": LocalImageStorage(settings.image_storage_root),
    }
    pending = False
    for kind, path in files:
        try:
            stores[kind].delete(path)
        except (OSError, ValueError):
            pending = True
            logger.exception(
                "Deleted content %s: %s file cleanup failed: %s", content_id, kind, path
            )
    return ContentDeleted(content_id=content_id, file_cleanup_pending=pending)
