"""Add image_assets table and thumbnail_image_id to contents and curricula.

Revision ID: 0002_thumbnail_support
Revises: 0001_initial_schema
"""

from alembic import op

revision: str = "0002_thumbnail_support"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        r"""
CREATE TABLE sasu.image_assets (
    image_asset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    storage_path varchar(1024) NOT NULL UNIQUE
        CHECK (btrim(storage_path) <> '' AND storage_path NOT LIKE '%..%'),
    mime_type varchar(100) NOT NULL
        CHECK (mime_type IN ('image/jpeg','image/png','image/webp')),
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    created_at timestamptz NOT NULL DEFAULT now()
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.image_assets IS '썸네일 등 정적 이미지 파일 메타데이터'
"""
    )
    op.execute(
        r"""
ALTER TABLE sasu.contents
    ADD COLUMN thumbnail_image_id uuid
        REFERENCES sasu.image_assets (image_asset_id) ON DELETE SET NULL
"""
    )
    op.execute(
        r"""
ALTER TABLE sasu.curricula
    ADD COLUMN thumbnail_image_id uuid
        REFERENCES sasu.image_assets (image_asset_id) ON DELETE SET NULL
"""
    )


def downgrade() -> None:
    op.execute(
        r"""ALTER TABLE sasu.curricula DROP COLUMN IF EXISTS thumbnail_image_id"""
    )
    op.execute(
        r"""ALTER TABLE sasu.contents DROP COLUMN IF EXISTS thumbnail_image_id"""
    )
    op.execute(r"""DROP TABLE IF EXISTS sasu.image_assets""")
