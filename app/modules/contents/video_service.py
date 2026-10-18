import logging
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import BinaryIO
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.integrations.storage import EmptyUploadError, LocalVideoStorage
from app.integrations.video_processing import (
    InvalidVideoError,
    UnsupportedVideoError,
    VideoInspectionTimeoutError,
    VideoInspector,
    VideoMetadata,
    VideoProcessingUnavailableError,
)
from app.modules.contents import repository
from app.modules.contents.models import ContentStatus, VideoAsset
from app.modules.contents.schemas import VideoInfo, VideoQuery
from app.modules.users.models import UserRole
from app.modules.users.repository import get_user
from app.modules.users.service import require_admin

logger = logging.getLogger(__name__)


def upload_video(
    session: Session,
    actor_id: int,
    content_id: int,
    stream: BinaryIO,
    storage: LocalVideoStorage,
    inspector: VideoInspector,
    original_name: str,
    expected_media_revision: str | None = None,
) -> VideoInfo:
    saved_path = None
    old_path = None
    try:
        with session.begin():
            require_admin(session, actor_id)
            content = repository.get_content_for_update(session, content_id)
            if content is None:
                raise ApiError(404, "CONTENT_NOT_FOUND", "콘텐츠가 없습니다.")
            old_asset = (
                session.get(VideoAsset, content.video_asset_id) if content.video_asset_id else None
            )
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
            old_path = old_asset.storage_path if old_asset else None
            original_name = PureWindowsPath(original_name).name
            if not original_name or len(original_name) > 255:
                raise ApiError(422, "INVALID_FILENAME", "파일명은 1~255자여야 합니다.")
            stream.seek(0)
            try:
                metadata = VideoMetadata.model_validate(inspector.inspect(stream))
            except ValidationError as exc:
                raise ApiError(
                    502, "INVALID_VIDEO_METADATA", "영상 검증 기능의 반환값이 올바르지 않습니다."
                ) from exc
            # 검사가 스트림을 읽었더라도 전체 파일을 처음부터 저장한다.
            stream.seek(0)
            saved = storage.save(stream)
            saved_path = saved.relative_path
            asset = VideoAsset(
                video_asset_id=uuid4(),
                storage_path=saved_path,
                original_name=original_name,
                mime_type=metadata.mime_type,
                size_bytes=saved.size_bytes,
                duration_seconds=metadata.duration_seconds,
            )
            repository.attach_video(session, content, asset)
            revision = str(asset.video_asset_id)
            result = VideoInfo(
                content_id=content.content_id,
                video_url=(
                    f"/api/contents/{content.content_id}/video?revision={revision}"
                    + (
                        f"&preview=true&actor_id={actor_id}"
                        if content.status == ContentStatus.DRAFT
                        else ""
                    )
                ),
                video_duration=float(asset.duration_seconds),
                media_revision=revision,
                status=content.status,
            )
    except Exception as exc:
        if saved_path is not None:
            try:
                storage.delete(saved_path)
            except OSError:
                logger.exception("DB 저장 실패 후 업로드 파일 정리에 실패했습니다.")
        if isinstance(exc, VideoProcessingUnavailableError):
            raise ApiError(
                503,
                "VIDEO_PROCESSING_UNAVAILABLE",
                "영상 검사 도구를 사용할 수 없습니다.",
            ) from exc
        if isinstance(exc, UnsupportedVideoError):
            raise ApiError(
                415, "UNSUPPORTED_MEDIA_TYPE", "MP4 영상 파일만 업로드할 수 있습니다."
            ) from exc
        if isinstance(exc, InvalidVideoError):
            raise ApiError(
                422, "INVALID_VIDEO", "영상 파일의 형식·스트림·길이를 확인할 수 없습니다."
            ) from exc
        if isinstance(exc, VideoInspectionTimeoutError):
            raise ApiError(
                422, "VIDEO_INSPECTION_TIMEOUT", "영상 검사 제한 시간을 초과했습니다."
            ) from exc
        if isinstance(exc, EmptyUploadError):
            raise ApiError(422, "EMPTY_UPLOAD", "빈 파일은 업로드할 수 없습니다.") from exc
        if isinstance(exc, (OSError, SQLAlchemyError)):
            raise ApiError(
                500, "INTERNAL_ERROR", "영상 파일 또는 콘텐츠 저장에 실패했습니다."
            ) from exc
        raise
    # 방문 기록은 이전 자산 UUID를 참조하므로 자산 행은 보존한다.
    # 구 파일만 커밋 성공 뒤 제거하며, 정리 실패가 이미 성공한 교체를 실패로 바꾸지는 않는다.
    if old_path is not None:
        try:
            storage.delete(old_path)
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
                actor = get_user(session, query.actor_id)
                if actor is None:
                    raise ApiError(404, "USER_NOT_FOUND", "행위자 사용자가 없습니다.")
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
            result = VideoStream(opened, start, end, size, partial)
        return result
    except Exception as exc:
        if opened is not None:
            opened.close()
        if isinstance(exc, SQLAlchemyError):
            raise ApiError(500, "INTERNAL_ERROR", "영상 조회에 실패했습니다.") from exc
        raise
