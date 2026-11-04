"""Separate private content and allow deletion of an entire content aggregate.

Revision ID: 0003_content_visibility_delete
Revises: 0002_thumbnail_support
"""

from alembic import op

revision = "0003_content_visibility_delete"
down_revision = "0002_thumbnail_support"
branch_labels = None
depends_on = None

_OWNED_FOREIGN_KEYS = (
    ("quizzes", "content_id", "contents", "content_id"),
    ("quiz_versions", "quiz_id", "quizzes", "quiz_id"),
    ("quiz_options", "quiz_version_id", "quiz_versions", "quiz_version_id"),
)


def _foreign_keys(action: str) -> None:
    for table, column, parent, parent_column in _OWNED_FOREIGN_KEYS:
        name = op.f(f"{table}_{column}_fkey")
        op.drop_constraint(name, table, schema="sasu", type_="foreignkey")
        op.create_foreign_key(
            name,
            table,
            parent,
            [column],
            [parent_column],
            source_schema="sasu",
            referent_schema="sasu",
            ondelete=action,
        )


def _progress_view(*, private_visible: bool) -> None:
    condition = (
        ""
        if private_visible
        else """
        AND EXISTS (SELECT 1 FROM sasu.contents x
                    WHERE x.content_id = i.content_id AND x.status <> 'PRIVATE')
    """
    )
    op.execute(f"""
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
LEFT JOIN sasu.curriculum_items i ON i.curriculum_id = c.curriculum_id {condition}
LEFT JOIN sasu.contents content ON content.content_id = i.content_id
LEFT JOIN sasu.watch_records w ON w.user_id = u.user_id AND w.content_id = i.content_id
LEFT JOIN sasu.quizzes q ON q.content_id = i.content_id
LEFT JOIN correct_quizzes correct ON correct.user_id = u.user_id AND correct.quiz_id = q.quiz_id
GROUP BY u.user_id, u.learning_epoch, c.curriculum_id
""")


def upgrade() -> None:
    op.drop_constraint(op.f("contents_status_check"), "contents", schema="sasu", type_="check")
    op.create_check_constraint(
        op.f("contents_status_check"),
        "contents",
        "status IN ('DRAFT', 'PUBLISHED', 'PRIVATE')",
        schema="sasu",
    )
    op.execute(
        "COMMENT ON COLUMN sasu.contents.status IS "
        "'DRAFT 작성 중 / PUBLISHED 공개 / PRIVATE 비공개'"
    )
    _foreign_keys("CASCADE")

    # 자식만 지워 이력을 바꾸는 행위는 계속 금지한다. 부모가 이미 삭제된
    # FK CASCADE 안에서만 버전·보기 DELETE를 허용하며 UPDATE는 언제나 거절한다.
    op.execute("""
CREATE FUNCTION sasu.guard_quiz_history_change() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF TG_TABLE_NAME = 'quiz_versions' THEN
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
    op.execute("""
CREATE FUNCTION sasu.guard_quiz_delete() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM sasu.contents WHERE content_id = OLD.content_id) THEN
        RAISE EXCEPTION 'Delete the owning content instead of quiz %', OLD.quiz_id
            USING ERRCODE = '23514';
    END IF;
    RETURN OLD;
END;
$$
""")
    op.execute("""
CREATE TRIGGER guard_quiz_delete BEFORE DELETE ON sasu.quizzes
FOR EACH ROW EXECUTE FUNCTION sasu.guard_quiz_delete()
""")
    for table in ("quiz_versions", "quiz_options"):
        op.execute(f"DROP TRIGGER immutable_{table} ON sasu.{table}")
        op.execute(f"""
CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON sasu.{table}
FOR EACH ROW EXECUTE FUNCTION sasu.guard_quiz_history_change()
""")
    op.execute("""
CREATE TABLE sasu.asset_cleanup_jobs (
    job_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_kind varchar(5) NOT NULL CHECK (asset_kind IN ('video', 'image')),
    storage_path varchar(1024) NOT NULL CHECK (btrim(storage_path) <> ''),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (asset_kind, storage_path)
)
""")
    _progress_view(private_visible=False)


def downgrade() -> None:
    op.execute("""
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM sasu.contents WHERE status = 'PRIVATE')
       OR EXISTS (SELECT 1 FROM sasu.asset_cleanup_jobs) THEN
        RAISE EXCEPTION 'Resolve PRIVATE contents and pending asset cleanup before downgrade';
    END IF;
END $$
""")
    _progress_view(private_visible=True)
    op.execute("DROP TABLE sasu.asset_cleanup_jobs")
    for table in ("quiz_versions", "quiz_options"):
        op.execute(f"DROP TRIGGER immutable_{table} ON sasu.{table}")
        op.execute(f"""
CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON sasu.{table}
FOR EACH ROW EXECUTE FUNCTION sasu.reject_immutable_change()
""")
    op.execute("DROP TRIGGER guard_quiz_delete ON sasu.quizzes")
    op.execute("DROP FUNCTION sasu.guard_quiz_delete()")
    op.execute("DROP FUNCTION sasu.guard_quiz_history_change()")
    _foreign_keys("RESTRICT")
    op.drop_constraint(op.f("contents_status_check"), "contents", schema="sasu", type_="check")
    op.create_check_constraint(
        op.f("contents_status_check"),
        "contents",
        "status IN ('DRAFT', 'PUBLISHED')",
        schema="sasu",
    )
    op.execute("COMMENT ON COLUMN sasu.contents.status IS '공개 상태'")
