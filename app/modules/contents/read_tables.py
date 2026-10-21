"""임시 조회용 정의: 다른 모듈의 정식 모델로 참조를 교체한 뒤 삭제한다.

contents/repository.py의 참조를 교체하고 조회 테스트를 확인한 뒤 제거한다.
content_metrics는 DB 뷰이므로 별도의 조회 정의로 이전해야 한다.
Base.metadata에 등록하지 않는다. 테이블·뷰 생성은 기존 Alembic이 담당하며,
여기서는 퀴즈·커리큘럼·학습 기록의 쓰기 모델이나 기능을 구현하지 않는다.
"""

from sqlalchemy import BigInteger, Column, DateTime, MetaData, String, Table

metadata = MetaData(schema="sasu")

content_metrics = Table(
    "content_metrics",
    metadata,
    Column("content_id", BigInteger),
    Column("view_count", BigInteger),
    Column("like_count", BigInteger),
)
quizzes = Table(
    "quizzes",
    metadata,
    Column("content_id", BigInteger),
    Column("current_version_id", BigInteger),
)
curricula = Table(
    "curricula",
    metadata,
    Column("curriculum_id", BigInteger),
    Column("title", String(200)),
)
curriculum_items = Table(
    "curriculum_items",
    metadata,
    Column("curriculum_id", BigInteger),
    Column("content_id", BigInteger),
)
saved_contents = Table(
    "saved_contents",
    metadata,
    Column("user_id", BigInteger),
    Column("content_id", BigInteger),
)
watch_records = Table(
    "watch_records",
    metadata,
    Column("user_id", BigInteger),
    Column("content_id", BigInteger),
    Column("completed_at", DateTime(timezone=True)),
)
