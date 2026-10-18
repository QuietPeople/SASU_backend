"""FastAPI 애플리케이션 진입점. 개별 API는 모듈에서 구현한다."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.db.models import load_models
from app.db.session import check_database_connection, close_database
from app.integrations.ffmpeg import ffmpeg_available
from app.integrations.storage import LocalVideoStorage

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    application.state.settings = settings
    load_models()
    try:
        await run_in_threadpool(check_database_connection)
        settings.video_storage_root.mkdir(parents=True, exist_ok=True)
        storage = LocalVideoStorage(settings.video_storage_root)
        storage.ensure_ready()
        removed = storage.cleanup_stale_temp()
        if removed:
            logger.info("남은 업로드 임시 파일 %d개를 정리했습니다.", removed)
        if not ffmpeg_available():
            logger.warning("ffmpeg/ffprobe가 없어 영상 업로드가 503으로 실패합니다.")
        yield
    finally:
        await run_in_threadpool(close_database)


app = FastAPI(
    title="SASU Backend API",
    description="SASU 학습자·관리자 기능을 제공하는 백엔드 API입니다.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={
        "displayRequestDuration": True,
        "filter": True,
    },
)
register_exception_handlers(app)
app.include_router(api_router)
