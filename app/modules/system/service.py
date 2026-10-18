"""DB와 영상 저장소를 독립적으로 확인하고 민감한 오류 정보는 응답에서 제외한다."""

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import check_database_connection
from app.integrations.storage import check_video_storage_access
from app.modules.system.schemas import Health


def get_health() -> Health:
    database = "ok"
    video_storage = "ok"
    try:
        check_database_connection()
    except (SQLAlchemyError, OSError):
        database = "unavailable"
    try:
        check_video_storage_access(get_settings().video_storage_root)
    except (OSError, ValueError):
        video_storage = "unavailable"
    return Health(
        status="ok" if database == video_storage == "ok" else "unavailable",
        database=database,
        video_storage=video_storage,
    )
