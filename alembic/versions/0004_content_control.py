"""Allow quiz history deletion with its owning content only."""

from alembic import op

revision = "0004_content_control"
down_revision = "0003_event_retry_keys"
branch_labels = None
depends_on = None


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


def downgrade():
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
