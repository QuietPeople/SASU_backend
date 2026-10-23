from sqlalchemy import BigInteger, Column, MetaData, String, Table

metadata = MetaData(schema="sasu")
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
