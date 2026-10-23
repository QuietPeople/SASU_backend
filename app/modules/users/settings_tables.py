from sqlalchemy import BigInteger, Column, Integer, MetaData, SmallInteger, String, TIMESTAMP, Table

metadata = MetaData()

user_settings = Table(
    "user_settings",
    metadata,
    Column("user_id", BigInteger, primary_key=True),
    Column("onboarding_status", String(12)),
    Column("review_interval", SmallInteger),
    Column("last_content_id", BigInteger),
    Column("learning_epoch", Integer),
    Column("updated_at", TIMESTAMP(timezone=True)),
    schema="sasu",
)

user_interests = Table(
    "user_interests",
    metadata,
    Column("user_id", BigInteger),
    Column("category_id", BigInteger),
    schema="sasu",
)
