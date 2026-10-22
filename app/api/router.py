"""모듈별 라우터를 /api 아래 통합한다. 기능 구현 시 include_router로 연결한다."""

from fastapi import APIRouter

from app.modules.admin.router import router as admin_router
from app.modules.categories.router import router as categories_router
from app.modules.contents.router import router as contents_router
from app.modules.curricula.router import router as curricula_router
from app.modules.likes.router import router as likes_router
from app.modules.questions.router import router as questions_router
from app.modules.responses.router import router as responses_router
from app.modules.system.router import router as system_router
from app.modules.tags.router import router as tags_router
from app.modules.users.router import router as users_router
from app.modules.users.settings_router import router as user_settings_router

api_router = APIRouter(prefix="/api")
api_router.include_router(admin_router)
api_router.include_router(categories_router)
api_router.include_router(contents_router)
api_router.include_router(tags_router)
api_router.include_router(questions_router)
api_router.include_router(curricula_router)
api_router.include_router(likes_router)
api_router.include_router(system_router)
api_router.include_router(users_router)
api_router.include_router(user_settings_router)
api_router.include_router(responses_router)
