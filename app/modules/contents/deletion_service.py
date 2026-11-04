import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.contents import deletion_repository as repository
from app.modules.contents.asset_cleanup import cleanup_assets
from app.modules.contents.schemas import ContentDelete
from app.modules.users.service import require_admin

logger = logging.getLogger(__name__)


def delete_content(
    session: Session, actor_id: int, content_id: int, request: ContentDelete
) -> None:
    try:
        with session.begin():
            require_admin(session, actor_id)
            if not request.confirm:
                raise ApiError(
                    422, "DELETE_CONFIRMATION_REQUIRED", "콘텐츠 영구 삭제 확인이 필요합니다."
                )
            content = repository.lock_target(session, content_id)
            if content is None:
                raise ApiError(404, "CONTENT_NOT_FOUND", "콘텐츠가 없습니다.")
            curriculum_ids = repository.lock_dependents(session, content_id)
            videos = repository.video_asset_ids(session, content)
            thumbnail = content.thumbnail_image_id
            repository.delete_records(session, content_id, curriculum_ids)
            # 퀴즈·전체 버전·보기만 부모 삭제의 FK CASCADE로 함께 제거한다.
            session.delete(content)
            session.flush()
            jobs = repository.delete_assets(session, videos, thumbnail)
    except SQLAlchemyError as exc:
        if getattr(getattr(exc, "orig", None), "sqlstate", None) in {"55P03", "40P01"}:
            raise ApiError(
                409, "CONTENT_IN_USE", "다른 작업이 처리 중입니다. 잠시 후 다시 삭제해 주세요."
            ) from exc
        raise ApiError(500, "INTERNAL_ERROR", "콘텐츠 삭제에 실패했습니다.") from exc
    try:
        cleanup_assets(session, jobs)
    except (SQLAlchemyError, OSError):
        # 이미 삭제된 콘텐츠를 실패 응답으로 돌리지 않는다. 작업 행은 커밋되어 있다.
        logger.exception("콘텐츠 삭제 후 파일 정리 작업을 재시도해야 합니다.")
