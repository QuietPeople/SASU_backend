"""별도 임시 이력 경로·SQLite에서 Alembic 템플릿과 실행 환경을 검증한다."""

import ast
import shutil
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.core.config import PROJECT_ROOT


def test_revision_template_and_migration_round_trip(tmp_path):
    migration_dir = tmp_path / "alembic"
    # 실제 이력은 PostgreSQL 전용이다. 이 테스트는 공통 템플릿·env.py만 검증한다.
    shutil.copytree(
        PROJECT_ROOT / "alembic",
        migration_dir,
        ignore=shutil.ignore_patterns("versions", "__pycache__"),
    )
    (migration_dir / "versions").mkdir()
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
