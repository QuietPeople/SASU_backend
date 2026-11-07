"""관리자 콘텐츠 전체 영구 삭제와 커밋 이후 파일 정리."""

import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ApiError, check_edit_version
from app.integrations.storage import LocalImageStorage, LocalVideoStorage
from app.modules.contents import lifecycle_repository, repository, service
from app.modules.contents.schemas import (
    ContentDelete,
    ContentDeleted,
)
from app.modules.users.service import require_admin

logger = logging.getLogger(__name__)


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
