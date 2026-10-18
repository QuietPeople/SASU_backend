"""로컬 .env와 컨테이너 환경변수에서 공통 설정을 읽고 검증한다."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env에는 Compose 전용 이미지 버전·포트도 포함된다.
        populate_by_name=True,
        hide_input_in_errors=True,
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    db_host: str = Field(default="localhost", min_length=1)
    db_port: int = Field(
        default=5432,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("DB_PORT", "POSTGRES_PORT"),
    )
    db_name: str = Field(
        default="sasu", min_length=1, validation_alias=AliasChoices("DB_NAME", "POSTGRES_DB")
    )
    db_user: str = Field(
        default="sasu", min_length=1, validation_alias=AliasChoices("DB_USER", "POSTGRES_USER")
    )
    db_password: SecretStr = Field(
        min_length=1, validation_alias=AliasChoices("DB_PASSWORD", "POSTGRES_PASSWORD")
    )
    db_echo: bool = False
    db_connect_timeout: int = Field(default=5, ge=1, le=60)
    video_storage_root: Path = PROJECT_ROOT / "storage" / "videos"
    # 영상 업로드 정책(데이터 처리). 숏폼 기준 제안값이며 .env로 바꿀 수 있다.
    video_max_mb: int = Field(default=200, ge=1, le=2048)
    video_min_seconds: float = Field(default=1.0, gt=0)
    video_max_seconds: float = Field(default=180.0, gt=0)

    @field_validator("video_storage_root")
    @classmethod
    def resolve_storage_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else PROJECT_ROOT / value

    @property
    def database_url(self) -> URL:
        # 문자열 결합을 피하여 @·%·/ 등이 포함된 비밀번호도 그대로 전달한다.
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
