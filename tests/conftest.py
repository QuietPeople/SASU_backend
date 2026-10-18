"""실제 .env나 개발 DB를 사용하지 않는 공통 테스트 설정."""

import pytest

from app.core.config import Settings, get_settings
from app.db.session import close_database


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch, tmp_path):
    for key in (
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "LOG_LEVEL",
        "DB_ECHO",
        "DB_CONNECT_TIMEOUT",
        "VIDEO_STORAGE_ROOT",
        "VIDEO_MAX_MB",
        "VIDEO_MIN_SECONDS",
        "VIDEO_MAX_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DB_PASSWORD", "sasu-test-password")
    monkeypatch.setenv("VIDEO_STORAGE_ROOT", str(tmp_path / "videos"))
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    close_database()
    get_settings.cache_clear()
