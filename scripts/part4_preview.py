"""파트1 라우터 등록 전 로컬 통합 확인용 진입점.

uvicorn scripts.part4_preview:app --host 0.0.0.0 --port 8000
최종 병합 후에는 기존 app.main:app을 사용한다.
"""

from app.main import app
from app.modules.dashboard.router import router as dashboard_router
from app.modules.statistics.router import router as statistics_router

# 파트1이 등록 패치를 반영한 상태에서도 중복 등록하지 않는다.
existing = {getattr(route, "path", None) for route in app.routes}
if "/api/users/{user_id}/dashboard" not in existing:
    app.include_router(dashboard_router, prefix="/api")
if "/api/statistics" not in existing:
    app.include_router(statistics_router, prefix="/api")
