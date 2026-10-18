from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContentStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class VideoAsset(Base):
    __tablename__ = "video_assets"
    __table_args__ = {"schema": "sasu"}

    video_asset_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    storage_path: Mapped[str] = mapped_column(String(1024), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    duration_seconds: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Content(Base):
    __tablename__ = "contents"
    __table_args__ = {"schema": "sasu"}

    content_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), Identity(always=True), primary_key=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("sasu.categories.category_id", ondelete="RESTRICT")
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("sasu.app_users.user_id", ondelete="RESTRICT")
    )
    video_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sasu.video_assets.video_asset_id", ondelete="RESTRICT"), unique=True
    )
    title: Mapped[str | None] = mapped_column(String(200))
    core_content: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    reviewed_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, native_enum=False, length=12),
        default=ContentStatus.DRAFT,
        server_default=text("'DRAFT'"),
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    caution_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    caution_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentTag(Base):
    __tablename__ = "content_tags"
    __table_args__ = {"schema": "sasu"}

    content_id: Mapped[int] = mapped_column(
        ForeignKey("sasu.contents.content_id", ondelete="RESTRICT"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("sasu.tags.tag_id", ondelete="RESTRICT"), primary_key=True
    )
