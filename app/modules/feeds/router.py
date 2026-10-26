from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import ActorId, Database, ResourceId, reject_query_parameters
from app.core.exceptions import ErrorResponse
from app.modules.feeds import service
from app.modules.feeds.contracts import FeedRanker
from app.modules.feeds.schemas import Feed

router = APIRouter(
    prefix="/users/{user_id}/feed",
    tags=["피드"],
    responses={code: {"model": ErrorResponse} for code in (403, 404, 422, 500)},
)


@router.get(
    "",
    response_model=Feed,
    operation_id="API-CNT-01",
    summary="학습자 본인의 콘텐츠 피드 조회",
    description=(
        "공개·재생 가능한 전체 후보와 개인 상태를 반환하며 학습 기록을 변경하지 않습니다. "
        "X-Record-Generation 요청 헤더는 필요하지 않습니다. "
        "현재 추천 함수 연결 전 임시 최신순이며 추천 정책은 파트 2 연결 후 적용됩니다."
    ),
    dependencies=[Depends(reject_query_parameters)],
)
def get_feed(
    user_id: ResourceId,
    session: Database,
    actor_id: ActorId,
    ranker: Annotated[FeedRanker, Depends(service.get_feed_ranker)],
) -> Feed:
    return service.get_feed(session, actor_id, user_id, ranker)
