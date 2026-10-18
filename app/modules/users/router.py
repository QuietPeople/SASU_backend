"""행위자 헤더 없이 호출할 수 있는 목업 사용자 조회 API."""

from fastapi import APIRouter, Depends

from app.api.dependencies import Database, ResourceId, reject_query_parameters
from app.core.exceptions import ErrorResponse
from app.modules.users import service
from app.modules.users.schemas import User, UserList

router = APIRouter(
    prefix="/users",
    tags=["사용자"],
    dependencies=[Depends(reject_query_parameters)],
    responses={
        422: {"model": ErrorResponse, "description": "잘못된 요청"},
        500: {"model": ErrorResponse, "description": "내부 처리 실패"},
    },
)


@router.get("", response_model=UserList, summary="API-USR-01 목업 사용자 목록 조회")
def get_users(session: Database) -> UserList:
    return service.get_users(session)


@router.get(
    "/{user_id}",
    response_model=User,
    summary="API-USR-02 사용자 식별 정보 조회",
    responses={404: {"model": ErrorResponse, "description": "사용자 없음"}},
)
def get_user(user_id: ResourceId, session: Database) -> User:
    return service.get_user(session, user_id)
