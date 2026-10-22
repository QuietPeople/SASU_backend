from sqlalchemy import BigInteger, Column, Integer, MetaData, Numeric, String, TIMESTAMP, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

watch_visits = None  # raw access via text() SQL; ORM Table not needed for write path
watch_records = None  # same — queries use text() exclusively
