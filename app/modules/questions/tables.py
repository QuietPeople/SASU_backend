from sqlalchemy import BigInteger, Column, MetaData, Table

metadata = MetaData(schema="sasu")
quizzes = Table(
    "quizzes",
    metadata,
    Column("quiz_id", BigInteger),
    Column("content_id", BigInteger),
    Column("current_version_id", BigInteger),
)
