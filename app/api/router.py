from fastapi import APIRouter

from app.modules.categories.router import router as categories_router
from app.modules.contents.router import router as contents_router
from app.modules.tags.router import router as tags_router

api_router = APIRouter(prefix="/api")
api_router.include_router(categories_router)
api_router.include_router(contents_router)
api_router.include_router(tags_router)
