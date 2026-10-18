"""콘텐츠 영상 업로드·교체와 재생 파일 제공.

업로드한 파일의 검증·분석·정규화·저장은 데이터 처리 모듈(app.modules.videos)이 맡고,
여기서는 권한·revision 확인과 video_assets 연결(DB)만 처리한다.
영상 처리는 시간이 걸려 DB 트랜잭션 밖에서 수행하고, DB 저장이 실패하면 새 파일을 지운다.
"""

import logging
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.integrations.storage import LocalVideoStorage
from app.modules.contents import repository
from app.modules.contents.models import Content, ContentStatus, VideoAsset
from app.modules.contents.schemas import VideoInfo, VideoQuery
from app.modules.contents.urls import build_video_url
from app.modules.users.models import UserRole
from app.modules.users.service import get_actor, require_admin
from app.modules.videos.service import IngestedVideo, VideoIngestService

logger = logging.getLogger(__name__)


def _upload_target(
    session: Session, actor_id: int, content_id: int, expected_media_revision: str | None
) -> tuple[Content, VideoAsset | None]:
    """권한·콘텐츠·revision 확인. 영상 처리 전과 DB 연결 직전에 두 번 수행한다."""
    require_admin(session, actor_id)
    content = repository.get_content_for_update(session, content_id)
    if content is None:
        raise ApiError(404, "CONTENT_NOT_FOUND", "콘텐츠가 없습니다.")
    old_asset = session.get(VideoAsset, content.video_asset_id) if content.video_asset_id else None
    if old_asset is not None and expected_media_revision is None:
        raise ApiError(
            409,
            "VIDEO_ALREADY_EXISTS",
            "영상 교체에는 현재 expected_media_revision이 필요합니다.",
        )
    if expected_media_revision is not None and (
        old_asset is None or expected_media_revision != str(old_asset.video_asset_id)
    ):
        raise ApiError(
            409,
            "VIDEO_CHANGED",
            "영상이 변경되었습니다. 현재 revision을 다시 확인해 주세요.",
        )
    return content, old_asset


def upload_video(
    session: Session,
    actor_id: int,
    content_id: int,
    stream: BinaryIO,
    ingest: VideoIngestService,
    original_name: str,
    expected_media_revision: str | None = None,
) -> VideoInfo:
    # 1) 가벼운 검사 먼저: 권한·콘텐츠·revision이 틀리면 영상을 처리하지 않는다.
    with session.begin():
        _upload_target(session, actor_id, content_id, expected_media_revision)

    # 2) 영상 처리(트랜잭션 밖): 검증·분석·정규화·저장. 실패하면 파일이 남지 않는다.
    try:
        stream.seek(0)
        video: IngestedVideo = ingest.ingest(stream, original_name)
    except OSError as exc:
        raise ApiError(500, "INTERNAL_ERROR", "영상 파일 저장에 실패했습니다.") from exc

    # 3) DB 연결. 그 사이 다른 교체가 끝났을 수 있어 다시 확인한다.
    old_path = None
    try:
        with session.begin():
            content, old_asset = _upload_target(
                session, actor_id, content_id, expected_media_revision
            )
            old_path = old_asset.storage_path if old_asset else None
            asset = VideoAsset(
                video_asset_id=video.asset_id,
                storage_path=video.storage_path,
                original_name=video.original_name,
                mime_type=video.mime_type,
                size_bytes=video.size_bytes,
                duration_seconds=video.duration_decimal,
            )
            repository.attach_video(session, content, asset)
            revision = str(asset.video_asset_id)
            result = VideoInfo(
                content_id=content.content_id,
                video_url=build_video_url(
                    content.content_id,
                    revision,
                    preview_actor_id=actor_id if content.status == ContentStatus.DRAFT else None,
                ),
                video_duration=float(asset.duration_seconds),
                media_revision=revision,
                status=content.status,
            )
    except Exception as exc:
        video.discard()
        if isinstance(exc, (OSError, SQLAlchemyError)):
            raise ApiError(
                500, "INTERNAL_ERROR", "영상 파일 또는 콘텐츠 저장에 실패했습니다."
            ) from exc
        raise
    # 방문 기록은 이전 자산 UUID를 참조하므로 자산 행은 보존한다.
    # 구 파일만 커밋 성공 뒤 제거하며, 정리 실패가 이미 성공한 교체를 실패로 바꾸지는 않는다.
    if old_path is not None:
        try:
            ingest.storage.delete(old_path)
        except (OSError, ValueError):
            logger.exception("영상 교체 후 이전 파일 정리에 실패했습니다.")
    return result


@dataclass
class VideoStream:
    file: BinaryIO
    start: int
    end: int
    size: int
    partial: bool
    mime_type: str = "video/mp4"

    def close(self) -> None:
        self.file.close()

    def chunks(self) -> Iterator[bytes]:
        try:
            self.file.seek(self.start)
            remaining = self.end - self.start + 1
            while remaining > 0:
                chunk = self.file.read(min(remaining, 1024 * 1024))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
        finally:
            self.close()


def _range(header: str | None, size: int) -> tuple[int, int, bool]:
    # 명세에 따라 복수 Range는 무시하고 전체 파일을 제공한다.
    if header is None or "," in header:
        return 0, size - 1, False
    try:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
        if match is None or not any(match.groups()):
            raise ValueError
        first, last = match.groups()
        if first:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
        else:
            suffix = int(last)
            if suffix <= 0:
                raise ValueError
            start, end = max(0, size - suffix), size - 1
        if start >= size or start > end:
            raise ValueError
        return start, end, True
    except ValueError as exc:
        raise ApiError(
            416,
            "RANGE_NOT_SATISFIABLE",
            "요청한 영상 바이트 범위를 제공할 수 없습니다.",
            headers={
                "Content-Range": f"bytes */{size}",
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-store",
            },
        ) from exc


def get_video(
    session: Session,
    content_id: int,
    query: VideoQuery,
    storage: LocalVideoStorage,
    range_header: str | None,
) -> VideoStream:
    opened = None
    try:
        with session.begin():
            if query.preview:
                actor = get_actor(session, query.actor_id)
                if actor.role != UserRole.ADMIN:
                    raise ApiError(403, "EDITOR_VIEW_REQUIRED", "미리보기는 관리자만 가능합니다.")
            # 구 파일을 열기 전 교체가 완료되어 사라지는 경합을 피한다.
            content = repository.get_content(session, content_id, lock_for_video=True)
            if content is None or (not query.preview and content.status != ContentStatus.PUBLISHED):
                raise ApiError(404, "CONTENT_NOT_FOUND", "조회 가능한 콘텐츠가 없습니다.")
            asset = (
                session.get(VideoAsset, content.video_asset_id) if content.video_asset_id else None
            )
            if asset is None:
                raise ApiError(404, "VIDEO_NOT_FOUND", "영상 파일이 없습니다.")
            if query.revision is not None and query.revision != str(asset.video_asset_id):
                raise ApiError(
                    409, "VIDEO_CHANGED", "영상이 변경되었습니다. 현재 revision을 확인해 주세요."
                )
            try:
                path = storage.resolve_path(asset.storage_path)
                if not path.is_file():
                    raise FileNotFoundError
                opened = path.open("rb")
                size = os.fstat(opened.fileno()).st_size
                if size <= 0:
                    raise FileNotFoundError
            except (OSError, ValueError) as exc:
                raise ApiError(
                    404, "VIDEO_NOT_FOUND", "영상 파일이 없거나 접근할 수 없습니다."
                ) from exc
            start, end, partial = _range(range_header, size)
            result = VideoStream(opened, start, end, size, partial, asset.mime_type)
        return result
    except Exception as exc:
        if opened is not None:
            opened.close()
        if isinstance(exc, SQLAlchemyError):
            raise ApiError(500, "INTERNAL_ERROR", "영상 조회에 실패했습니다.") from exc
        raise
