"""별도 임시 DB에서 Alembic 템플릿과 변경 이력 적용을 검증한다."""

import ast
import shutil
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.core.config import PROJECT_ROOT


def test_revision_template_and_migration_round_trip(tmp_path):
    migration_dir = tmp_path / "alembic"
    shutil.copytree(PROJECT_ROOT / "alembic", migration_dir)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(migration_dir))
    revision = command.revision(config, message="infrastructure test")
    ast.parse(Path(revision.path).read_text(encoding="utf-8"))

    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                revision.revision
            )
            command.downgrade(config, "base")
            assert connection.scalar(text("SELECT count(*) FROM alembic_version")) == 0
    finally:
        engine.dispose()
