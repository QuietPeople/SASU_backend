"""첫 요청 시 검증된 환경 설정을 읽어 실제 프론트 origin만 허용한다."""

from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from app.core.config import get_settings


class ConfiguredCORSMiddleware(CORSMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(
            app,
            allow_origins=get_settings().cors_origins,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["X-Actor-Id", "X-Record-Generation", "Content-Type", "Range"],
            expose_headers=["Accept-Ranges", "Content-Range"],
        )
