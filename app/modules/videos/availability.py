from decimal import Decimal
from math import isfinite

from app.core.config import get_settings
from app.integrations.storage import LocalVideoStorage

PLAYABLE_MIME_TYPES = frozenset({"video/mp4", "video/webm"})


def is_video_available(
    storage_path: str | None,
    *,
    size_bytes: int | None,
    mime_type: str | None,
    duration_seconds: Decimal | float | None,
    storage: LocalVideoStorage | None = None,
) -> bool:
    """저장된 영상의 재생 가능 기준. 실제 스트림 제공 시에도 파일을 다시 검사한다."""
    if (
        not storage_path
        or size_bytes is None
        or size_bytes <= 0
        or mime_type not in PLAYABLE_MIME_TYPES
        or duration_seconds is None
        or not isfinite(duration_seconds)
        or duration_seconds <= 0
    ):
        return False
    try:
        storage = storage or LocalVideoStorage(get_settings().video_storage_root)
        path = storage.resolve_path(storage_path)
        return path.is_file() and path.stat().st_size == size_bytes
    except (OSError, RuntimeError, ValueError):
        return False


def is_video_row_available(row) -> bool:
    return is_video_available(
        row["storage_path"],
        size_bytes=row["size_bytes"],
        mime_type=row["mime_type"],
        duration_seconds=row["duration_seconds"],
    )
