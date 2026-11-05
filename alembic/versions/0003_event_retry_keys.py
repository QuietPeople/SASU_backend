"""Index alternate client event identifiers independently of event payload size."""

from alembic import op

revision = "0003_event_retry_keys"
down_revision = "0002_thumbnail_support"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE sasu.event_retry_keys (
        client_event_id uuid PRIMARY KEY,
        event_id uuid NOT NULL REFERENCES sasu.learning_events(event_id) ON DELETE CASCADE
    )""")
    op.execute("CREATE INDEX ix_event_retry_parent ON sasu.event_retry_keys(event_id)")
    op.execute("""INSERT INTO sasu.event_retry_keys(client_event_id, event_id)
        SELECT DISTINCT key::uuid, event_id FROM sasu.learning_events
        CROSS JOIN LATERAL jsonb_array_elements_text(metadata->'client_event_ids') AS keys(key)
    """)


def downgrade():
    op.execute("""UPDATE sasu.learning_events e SET metadata=jsonb_set(
        e.metadata, '{client_event_ids}', grouped.keys)
        FROM (SELECT event_id, jsonb_agg(client_event_id ORDER BY client_event_id) AS keys
              FROM sasu.event_retry_keys GROUP BY event_id) grouped
        WHERE e.event_id=grouped.event_id""")
    op.execute("DROP TABLE sasu.event_retry_keys")
