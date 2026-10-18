"""업로드용 ORM 조회와 USR-01·02 식별 정보 조회. 사용자 생성은 수행하지 않는다."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.users.models import User


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def list_users(session: Session):
    return (
        session.execute(
            text("SELECT user_id, display_name AS name, role FROM sasu.app_users ORDER BY user_id")
        )
        .mappings()
        .all()
    )


def find_user(session: Session, user_id: int):
    return (
        session.execute(
            text(
                "SELECT user_id, display_name AS name, role FROM sasu.app_users WHERE user_id = :id"
            ),
            {"id": user_id},
        )
        .mappings()
        .one_or_none()
    )
