"""콘텐츠·커리큘럼 썸네일 이미지 등록·제공·삭제."""

import uuid as _uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.integrations.storage import LocalImageStorage
from app.modules.contents.models import Content, ImageAsset
from app.modules.contents.repository import get_content_for_update
from app.modules.users.service import require_admin

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB

_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _detect_mime(head: bytes) -> str:
    if len(head) >= 3 and head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(head) >= 8 and head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return ""


def _validate(data: bytes) -> str:
    mime = _detect_mime(data[:12] if len(data) >= 12 else data)
    if not mime:
        raise ApiError(415, "UNSUPPORTED_IMAGE_TYPE", "JPEG·PNG·WebP 파일만 허용합니다.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ApiError(413, "IMAGE_TOO_LARGE", "이미지는 최대 10MB까지 허용합니다.")
    return mime


def _write(data: bytes, mime: str, storage: LocalImageStorage) -> str:
    """임시 파일로 저장 후 최종 경로로 이동. 실패 시 임시 파일 정리."""
    ext = _EXT[mime]
    relative_path = LocalImageStorage.new_relative_path(_uuid.uuid4(), ext)
    tmp = storage.temp_file(ext)
    try:
        tmp.write_bytes(data)
        storage.commit(tmp, relative_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return relative_path


def _delete_safe(storage: LocalImageStorage, path: str) -> None:
    try:
        storage.delete(path)
    except Exception:
        pass


# ── 콘텐츠 썸네일 ─────────────────────────────────────────────────────────────


def put_content_thumbnail(session: Session, content_id: int, actor_id: int, data: bytes) -> None:
    mime = _validate(data)
    storage = LocalImageStorage(get_settings().image_storage_root)
    relative_path = _write(data, mime, storage)
    try:
        with session.begin():
            require_admin(session, actor_id)
            content = get_content_for_update(session, content_id)
            if content is None:
                raise ApiError(404, "CONTENT_NOT_FOUND", "콘텐츠가 없습니다.")
            old_path: str | None = None
            if content.thumbnail_image_id is not None:
                old = session.get(ImageAsset, content.thumbnail_image_id)
                if old is not None:
                    old_path = old.storage_path
                    session.delete(old)
                    session.flush()
            asset = ImageAsset(
                storage_path=relative_path,
                mime_type=mime,
                size_bytes=len(data),
            )
            session.add(asset)
            session.flush()
            content.thumbnail_image_id = asset.image_asset_id
        if old_path:
            _delete_safe(storage, old_path)
    except Exception:
        _delete_safe(storage, relative_path)
        raise


def get_content_thumbnail(
    session: Session, content_id: int, *, preview: bool = False, actor_id: int | None = None
) -> tuple[bytes, str]:
    with session.begin():
        content = session.get(Content, content_id)
        if content is None or content.thumbnail_image_id is None:
            raise ApiError(404, "THUMBNAIL_NOT_FOUND", "등록된 썸네일이 없습니다.")
        if content.status == "PRIVATE":
            if not preview or actor_id is None:
                raise ApiError(404, "THUMBNAIL_NOT_FOUND", "등록된 썸네일이 없습니다.")
            require_admin(session, actor_id)
        asset = session.get(ImageAsset, content.thumbnail_image_id)
        if asset is None:
            raise ApiError(404, "THUMBNAIL_NOT_FOUND", "등록된 썸네일이 없습니다.")
        storage_path, mime_type = asset.storage_path, asset.mime_type
    storage = LocalImageStorage(get_settings().image_storage_root)
    try:
        return storage.resolve_path(storage_path).read_bytes(), mime_type
    except (OSError, ValueError) as exc:
        raise ApiError(404, "THUMBNAIL_NOT_FOUND", "썸네일 파일을 찾을 수 없습니다.") from exc


def delete_content_thumbnail(session: Session, content_id: int, actor_id: int) -> None:
    with session.begin():
        require_admin(session, actor_id)
        content = get_content_for_update(session, content_id)
        if content is None:
            raise ApiError(404, "CONTENT_NOT_FOUND", "콘텐츠가 없습니다.")
        if content.thumbnail_image_id is None:
            raise ApiError(404, "THUMBNAIL_NOT_FOUND", "등록된 썸네일이 없습니다.")
        asset = session.get(ImageAsset, content.thumbnail_image_id)
        old_path = asset.storage_path if asset else None
        content.thumbnail_image_id = None
        if asset:
            session.delete(asset)
    if old_path:
        _delete_safe(LocalImageStorage(get_settings().image_storage_root), old_path)


# ── 커리큘럼 썸네일 ───────────────────────────────────────────────────────────


def put_curriculum_thumbnail(
    session: Session, curriculum_id: int, actor_id: int, data: bytes
) -> None:
    mime = _validate(data)
    storage = LocalImageStorage(get_settings().image_storage_root)
    relative_path = _write(data, mime, storage)
    try:
        with session.begin():
            require_admin(session, actor_id)
            row = (
                session.execute(
                    text(
                        "SELECT thumbnail_image_id FROM sasu.curricula "
                        "WHERE curriculum_id = :id FOR UPDATE"
                    ),
                    {"id": curriculum_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise ApiError(404, "CURRICULUM_NOT_FOUND", "커리큘럼이 없습니다.")
            old_path: str | None = None
            if row["thumbnail_image_id"] is not None:
                old = session.get(ImageAsset, row["thumbnail_image_id"])
                if old is not None:
                    old_path = old.storage_path
                    session.delete(old)
                    session.flush()
            asset = ImageAsset(
                storage_path=relative_path,
                mime_type=mime,
                size_bytes=len(data),
            )
            session.add(asset)
            session.flush()
            session.execute(
                text(
                    "UPDATE sasu.curricula SET thumbnail_image_id = :tid WHERE curriculum_id = :id"
                ),
                {"tid": asset.image_asset_id, "id": curriculum_id},
            )
        if old_path:
            _delete_safe(storage, old_path)
    except Exception:
        _delete_safe(storage, relative_path)
        raise


def get_curriculum_thumbnail(session: Session, curriculum_id: int) -> tuple[bytes, str]:
    with session.begin():
        row = (
            session.execute(
                text("SELECT thumbnail_image_id FROM sasu.curricula WHERE curriculum_id = :id"),
                {"id": curriculum_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["thumbnail_image_id"] is None:
            raise ApiError(404, "THUMBNAIL_NOT_FOUND", "등록된 썸네일이 없습니다.")
        asset = session.get(ImageAsset, row["thumbnail_image_id"])
        if asset is None:
            raise ApiError(404, "THUMBNAIL_NOT_FOUND", "등록된 썸네일이 없습니다.")
        storage_path, mime_type = asset.storage_path, asset.mime_type
    storage = LocalImageStorage(get_settings().image_storage_root)
    try:
        return storage.resolve_path(storage_path).read_bytes(), mime_type
    except (OSError, ValueError) as exc:
        raise ApiError(404, "THUMBNAIL_NOT_FOUND", "썸네일 파일을 찾을 수 없습니다.") from exc


def delete_curriculum_thumbnail(session: Session, curriculum_id: int, actor_id: int) -> None:
    with session.begin():
        require_admin(session, actor_id)
        row = (
            session.execute(
                text(
                    "SELECT thumbnail_image_id FROM sasu.curricula "
                    "WHERE curriculum_id = :id FOR UPDATE"
                ),
                {"id": curriculum_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ApiError(404, "CURRICULUM_NOT_FOUND", "커리큘럼이 없습니다.")
        if row["thumbnail_image_id"] is None:
            raise ApiError(404, "THUMBNAIL_NOT_FOUND", "등록된 썸네일이 없습니다.")
        asset = session.get(ImageAsset, row["thumbnail_image_id"])
        old_path = asset.storage_path if asset else None
        if asset:
            session.delete(asset)
        session.execute(
            text("UPDATE sasu.curricula SET thumbnail_image_id = NULL WHERE curriculum_id = :id"),
            {"id": curriculum_id},
        )
    if old_path:
        _delete_safe(LocalImageStorage(get_settings().image_storage_root), old_path)
