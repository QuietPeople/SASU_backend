"""삭제 후 남은 파일 재정리: python -m app.jobs.asset_cleanup"""

from app.db.session import close_database, get_session_factory
from app.modules.contents.asset_cleanup import cleanup_assets


def main() -> None:
    try:
        with get_session_factory()() as session:
            removed = cleanup_assets(session)
            print(f"파일 정리 완료: {removed}개 (최대 100개 처리, 실패 작업은 유지)")
    finally:
        close_database()


if __name__ == "__main__":
    main()
