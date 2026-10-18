"""인증 없이 호출하는 서비스 준비 상태 조회 API."""

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from app.api.dependencies import reject_query_parameters
from app.core.exceptions import ErrorDetail, ErrorResponse
from app.modules.system import service
from app.modules.system.schemas import Health, UnavailableHealth

router = APIRouter(tags=["서비스 상태"])


@router.get(
    "/health",
    response_model=Health,
    summary="API-SYS-01 서비스 상태 확인",
    description=(
        "DB 연결과 영상 저장 루트의 읽기·쓰기를 확인합니다. 행위자 헤더가 필요하지 않습니다."
    ),
    dependencies=[Depends(reject_query_parameters)],
    responses={
        503: {"model": UnavailableHealth, "description": "DB 또는 영상 저장소 준비 실패"},
        422: {"model": ErrorResponse, "description": "미정의 조회 조건"},
        500: {"model": ErrorResponse, "description": "내부 처리 실패"},
    },
)
def get_health(response: Response):
    health = service.get_health()
    response.headers["Cache-Control"] = "no-store"
    if health.status == "unavailable":
        unavailable = UnavailableHealth(
            **health.model_dump(),
            detail=ErrorDetail(
                code="SERVICE_UNAVAILABLE", message="DB 또는 영상 저장소가 준비되지 않았습니다."
            ),
        )
        return JSONResponse(
            status_code=503,
            content=unavailable.model_dump(exclude_none=True),
            headers={"Cache-Control": "no-store"},
        )
    return health
