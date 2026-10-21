from sqlalchemy import BigInteger, Column, DateTime, Integer, MetaData, Table, func

# 기존 테이블의 SQL 접근 정의이며, 실제 스키마 생성·변경은 Alembic이 관리한다.
metadata = MetaData(schema="sasu")

content_likes = Table(
    "content_likes",
    metadata,
    Column("user_id", BigInteger, primary_key=True),
    Column("learning_epoch", Integer, nullable=False),
    Column("content_id", BigInteger, primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
