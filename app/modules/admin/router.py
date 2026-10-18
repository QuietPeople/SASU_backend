"""관리자 HTTP 계약. 콘텐츠·사용자 경로도 관리자 모듈에서 제공한다."""

from fastapi import APIRouter, Depends

from app.api.dependencies import Database, ResourceId, reject_query_parameters
from app.core.exceptions import ErrorResponse
from app.core.security import require_admin
from app.modules.admin import service
from app.modules.admin.schemas import ReactionStats, ResetRequest, ResetResult

router = APIRouter(
    tags=["관리자"],
    dependencies=[Depends(require_admin), Depends(reject_query_parameters)],
    responses={
        403: {"model": ErrorResponse, "description": "관리자 역할 필요"},
        404: {"model": ErrorResponse, "description": "사용자 또는 대상 자료 없음"},
        422: {"model": ErrorResponse, "description": "잘못된 요청"},
        500: {"model": ErrorResponse, "description": "내부 처리 실패"},
    },
)


@router.get(
    "/contents/{content_id}/statistics/reactions",
    response_model=ReactionStats,
    summary="API-STA-04 반응·시청 통계 조회",
)
def get_reactions(content_id: ResourceId, session: Database) -> ReactionStats:
    return service.get_reaction_stats(session, content_id)


@router.post(
    "/users/{user_id}/test-records/reset",
    response_model=ResetResult,
    summary="API-TST-01 테스트 학습 기록 초기화",
    description=(
        "confirm=true와 현재 expected_record_generation이 필요합니다. "
        "API 세대는 0부터 시작하며 DB learning_epoch보다 1 작습니다. "
        "성공하면 대상 학습 기록만 삭제하고 등록 자료·사용자 설정은 보존합니다."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "JSON 구문 오류"},
        409: {"model": ErrorResponse, "description": "초기화 세대 불일치"},
    },
)
def reset_test_records(
    user_id: ResourceId, request: ResetRequest, session: Database
) -> ResetResult:
    return service.reset_records(session, user_id, request)
