from sqlalchemy.orm import Session

from app.modules.users.models import User


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)
