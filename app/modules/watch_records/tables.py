from sqlalchemy import BigInteger, Column, DateTime, Integer, MetaData, Numeric, Table

metadata = MetaData(schema="sasu")

watch_records = Table(
    "watch_records",
    metadata,
    Column("user_id", BigInteger, primary_key=True),
    Column("content_id", BigInteger, primary_key=True),
    Column("learning_epoch", Integer),
    Column("first_played_at", DateTime(timezone=True)),
    Column("last_watched_at", DateTime(timezone=True)),
    Column("view_counted_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("max_coverage_ratio", Numeric(9, 8)),
)
