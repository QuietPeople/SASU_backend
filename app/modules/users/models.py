from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Enum, Identity, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(StrEnum):
    LEARNER = "LEARNER"
    ADMIN = "ADMIN"


class User(Base):
    __tablename__ = "app_users"
    __table_args__ = {"schema": "sasu"}

    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), Identity(always=True), primary_key=True
    )
    username: Mapped[str] = mapped_column(String(32), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False, length=10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
