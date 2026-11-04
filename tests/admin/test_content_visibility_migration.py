"""기존 0002 DB의 행을 보존하는 업그레이드와 안전한 다운그레이드를 검증한다."""

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.core.config import PROJECT_ROOT


def test_upgrade_preserves_existing_rows_and_downgrade_guards_private_content(postgres_engine):
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    with postgres_engine.connect() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0002_thumbnail_support")
        connection.commit()
        user = connection.scalar(
            text("""
            INSERT INTO sasu.app_users (username, display_name, role)
            VALUES ('migration', '마이그레이션', 'ADMIN') RETURNING user_id
        """)
        )
        target = connection.scalar(
            text("""
            INSERT INTO sasu.contents (created_by_user_id, title)
            VALUES (:id, '보존할 초안') RETURNING content_id
        """),
            {"id": user},
        )
        connection.commit()
        command.upgrade(config, "head")
        assert (
            connection.scalar(
                text("SELECT title FROM sasu.contents WHERE content_id=:id"), {"id": target}
            )
            == "보존할 초안"
        )
        connection.execute(
            text("UPDATE sasu.contents SET status='PRIVATE' WHERE content_id=:id"), {"id": target}
        )
        with pytest.raises(DBAPIError), connection.begin_nested():
            command.downgrade(config, "0002_thumbnail_support")
        assert (
            connection.scalar(
                text("SELECT status FROM sasu.contents WHERE content_id=:id"), {"id": target}
            )
            == "PRIVATE"
        )
        connection.execute(
            text("UPDATE sasu.contents SET status='DRAFT' WHERE content_id=:id"), {"id": target}
        )
        connection.commit()
        connection.execute(
            text("""
            INSERT INTO sasu.asset_cleanup_jobs (asset_kind, storage_path)
            VALUES ('video', 'pending.mp4')
        """)
        )
        connection.commit()
        with pytest.raises(DBAPIError), connection.begin_nested():
            command.downgrade(config, "0002_thumbnail_support")
        assert connection.scalar(text("SELECT count(*) FROM sasu.asset_cleanup_jobs")) == 1
        connection.execute(text("DELETE FROM sasu.asset_cleanup_jobs"))
        connection.commit()
        command.downgrade(config, "0002_thumbnail_support")
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0002_thumbnail_support"
        )
        with pytest.raises(DBAPIError), connection.begin_nested():
            connection.execute(
                text("UPDATE sasu.contents SET status='PRIVATE' WHERE content_id=:id"),
                {"id": target},
            )
        connection.commit()
        command.upgrade(config, "head")
