"""DB 삭제 커밋 뒤 파일을 정리하고 실패한 작업은 DB에 남겨 재시도한다."""

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.storage import LocalImageStorage, LocalVideoStorage

logger = logging.getLogger(__name__)


def cleanup_assets(session: Session, job_ids: list[int] | None = None) -> int:
    if job_ids == []:
        return 0
    removed = 0
    settings = get_settings()
    stores = {
        "video": LocalVideoStorage(settings.video_storage_root),
        "image": LocalImageStorage(settings.image_storage_root),
    }
    with session.begin():
        jobs = (
            session.execute(
                text("""
            SELECT job_id, asset_kind, storage_path FROM sasu.asset_cleanup_jobs
            WHERE CAST(:ids AS bigint[]) IS NULL OR job_id = ANY(CAST(:ids AS bigint[]))
            ORDER BY job_id LIMIT 100 FOR UPDATE SKIP LOCKED
        """),
                {"ids": job_ids},
            )
            .mappings()
            .all()
        )
        for job in jobs:
            try:
                stores[job["asset_kind"]].delete(job["storage_path"])
            except (OSError, ValueError):
                logger.exception("콘텐츠 파일 정리 보류 job_id=%s", job["job_id"])
                continue
            session.execute(
                text("DELETE FROM sasu.asset_cleanup_jobs WHERE job_id = :id"),
                {"id": job["job_id"]},
            )
            removed += 1
    return removed
