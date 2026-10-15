"""환경변수 우선순위·입력 검증·DB 비밀번호 처리를 검증한다."""

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import PROJECT_ROOT, Settings


def test_special_characters_in_database_password(monkeypatch):
    password = "p@ss:/%#word"
    monkeypatch.setenv("DB_PASSWORD", password)
    settings = Settings()
    parsed = make_url(settings.database_url.render_as_string(hide_password=False))

    assert parsed.password == password
    assert password not in repr(settings)
    assert password not in str(settings.database_url)


def test_dotenv_and_container_environment_priority(monkeypatch, tmp_path):
    monkeypatch.delenv("DB_PASSWORD")
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "POSTGRES_DB=local_db\nPOSTGRES_USER=local_user\n"
        "POSTGRES_PASSWORD=local-secret\nPOSTGRES_PORT=5544\nPYTHON_VERSION=3.13\n",
        encoding="utf-8",
    )
    local = Settings(_env_file=dotenv)
    assert (local.db_name, local.db_user, local.db_port) == ("local_db", "local_user", 5544)

    monkeypatch.setenv("DB_HOST", "db")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_PASSWORD", "container-secret")
    container = Settings(_env_file=dotenv)
    assert (container.db_host, container.db_port) == ("db", 5432)
    assert container.db_password.get_secret_value() == "container-secret"


@pytest.mark.parametrize("value", ["0", "65536", "not-a-port"])
def test_invalid_database_port(monkeypatch, value):
    monkeypatch.setenv("DB_PORT", value)
    with pytest.raises(ValidationError):
        Settings()


def test_missing_or_empty_password_is_rejected(monkeypatch):
    monkeypatch.delenv("DB_PASSWORD")
    with pytest.raises(ValidationError):
        Settings()

    monkeypatch.setenv("DB_PASSWORD", "")
    with pytest.raises(ValidationError):
        Settings()


def test_relative_video_directory_is_project_relative(monkeypatch):
    monkeypatch.setenv("VIDEO_STORAGE_ROOT", "storage/videos")
    assert Settings().video_storage_root == PROJECT_ROOT / "storage/videos"
