"""Add private content and allow quiz history deletion with its owning content only."""

from alembic import op

revision = "0004_content_control"
down_revision = "0003_event_retry_keys"
branch_labels = None
depends_on = None


def _progress_view(exclude_private: bool) -> str:
    condition = (
        " AND EXISTS (SELECT 1 FROM sasu.contents x "
        "WHERE x.content_id=i.content_id AND x.status <> 'PRIVATE')"
        if exclude_private
        else ""
    )
    return (
        """
CREATE OR REPLACE VIEW sasu.curriculum_progress AS
WITH correct_quizzes AS (
    SELECT DISTINCT a.user_id, a.quiz_id FROM sasu.quiz_attempts a
    JOIN sasu.quiz_responses r ON r.attempt_id = a.attempt_id WHERE r.result = 'CORRECT'
)
SELECT u.user_id, u.learning_epoch, c.curriculum_id,
       count(i.content_id) AS total_steps,
       count(i.content_id) FILTER (WHERE content.status = 'PUBLISHED') AS available_steps,
       count(i.content_id) FILTER (
           WHERE w.completed_at IS NOT NULL AND correct.quiz_id IS NOT NULL
       ) AS completed_steps,
       (count(i.content_id) FILTER (
           WHERE w.completed_at IS NOT NULL AND correct.quiz_id IS NOT NULL
       ))::numeric / nullif(count(i.content_id), 0) AS progress_ratio
FROM sasu.user_settings u CROSS JOIN sasu.curricula c
LEFT JOIN sasu.curriculum_items i ON i.curriculum_id = c.curriculum_id
"""
        + condition
        + """
LEFT JOIN sasu.contents content ON content.content_id = i.content_id
LEFT JOIN sasu.watch_records w ON w.user_id = u.user_id AND w.content_id = i.content_id
LEFT JOIN sasu.quizzes q ON q.content_id = i.content_id
LEFT JOIN correct_quizzes correct ON correct.user_id = u.user_id AND correct.quiz_id = q.quiz_id
GROUP BY u.user_id, u.learning_epoch, c.curriculum_id
"""
    )


def _quiz_foreign_keys(action: str) -> None:
    for table, parent, column in (
        ("quizzes", "contents", "content_id"),
        ("quiz_versions", "quizzes", "quiz_id"),
        ("quiz_options", "quiz_versions", "quiz_version_id"),
    ):
        constraint = f"{table}_{column}_fkey"
        op.execute(f"ALTER TABLE sasu.{table} DROP CONSTRAINT {constraint}")
        op.execute(
            f"ALTER TABLE sasu.{table} ADD CONSTRAINT {constraint} "
            f"FOREIGN KEY ({column}) REFERENCES sasu.{parent}({column}) ON DELETE {action}"
        )


def upgrade():
    op.execute("ALTER TABLE sasu.contents DROP CONSTRAINT contents_status_check")
    op.execute("""ALTER TABLE sasu.contents ADD CONSTRAINT contents_status_check
        CHECK (status IN ('DRAFT', 'PUBLISHED', 'PRIVATE'))""")
    _quiz_foreign_keys("CASCADE")
    # Parent rows are already absent during FK cascades. Standalone history edits/deletes
    # remain forbidden; no session flag or trigger-disable operation bypasses immutability.
    op.execute("""
CREATE OR REPLACE FUNCTION sasu.reject_immutable_change() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF TG_TABLE_NAME = 'quizzes' THEN
            IF NOT EXISTS (SELECT 1 FROM sasu.contents WHERE content_id = OLD.content_id) THEN
                RETURN OLD;
            END IF;
        ELSIF TG_TABLE_NAME = 'quiz_versions' THEN
            IF NOT EXISTS (SELECT 1 FROM sasu.quizzes WHERE quiz_id = OLD.quiz_id) THEN
                RETURN OLD;
            END IF;
        ELSIF TG_TABLE_NAME = 'quiz_options' THEN
            IF NOT EXISTS (SELECT 1 FROM sasu.quiz_versions
                           WHERE quiz_version_id = OLD.quiz_version_id) THEN
                RETURN OLD;
            END IF;
        END IF;
    END IF;
    RAISE EXCEPTION '% rows are immutable; % is not allowed', TG_TABLE_NAME, TG_OP
        USING ERRCODE = '23514';
END;
$$
""")
    op.execute("""CREATE TRIGGER guard_quiz_deletion BEFORE DELETE ON sasu.quizzes
        FOR EACH ROW EXECUTE FUNCTION sasu.reject_immutable_change()""")
    op.execute(_progress_view(True))


def downgrade():
    # Fail atomically if PRIVATE rows remain; never silently change published visibility.
    op.execute("ALTER TABLE sasu.contents DROP CONSTRAINT contents_status_check")
    op.execute("""ALTER TABLE sasu.contents ADD CONSTRAINT contents_status_check
        CHECK (status IN ('DRAFT', 'PUBLISHED'))""")
    op.execute(_progress_view(False))
    op.execute("DROP TRIGGER guard_quiz_deletion ON sasu.quizzes")
    _quiz_foreign_keys("RESTRICT")
    op.execute("""
CREATE OR REPLACE FUNCTION sasu.reject_immutable_change() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
BEGIN
    RAISE EXCEPTION '% rows are immutable; % is not allowed', TG_TABLE_NAME, TG_OP
        USING ERRCODE = '23514';
END;
$$
""")
