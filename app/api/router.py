"""모듈별 라우터를 /api 아래 통합한다. 기능 구현 시 include_router로 연결한다."""

from fastapi import APIRouter

api_router = APIRouter(prefix="/api")
