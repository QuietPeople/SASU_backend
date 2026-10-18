"""영상 자산 테이블(sasu.video_assets) 매핑. 테이블 생성은 Alembic 0001이 담당한다."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Numeric, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VideoAsset(Base):
    __tablename__ = "video_assets"
    __table_args__ = {"schema": "sasu"}

    video_asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    storage_path: Mapped[str] = mapped_column(String(1024), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    duration_seconds: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
