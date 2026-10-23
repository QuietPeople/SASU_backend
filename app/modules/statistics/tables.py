from sqlalchemy import BigInteger, Column, MetaData, Table

# Alembic이 생성한 집계 뷰의 조회 정의이며 테이블 생성 대상으로 등록하지 않는다.
metadata = MetaData(schema="sasu")
content_metrics = Table(
    "content_metrics",
    metadata,
    Column("content_id", BigInteger),
    Column("view_count", BigInteger),
    Column("like_count", BigInteger),
    Column("saved_count", BigInteger),
)
