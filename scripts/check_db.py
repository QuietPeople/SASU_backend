"""python -m scripts.check_db로 현재 설정의 DB 연결을 확인한다."""

from app.core.config import get_settings
from app.db.session import check_database_connection, close_database


def main() -> None:
    settings = get_settings()
    try:
        check_database_connection()
        print(f"DB 연결 성공: {settings.db_host}:{settings.db_port}/{settings.db_name}")
    finally:
        close_database()


if __name__ == "__main__":
    main()
