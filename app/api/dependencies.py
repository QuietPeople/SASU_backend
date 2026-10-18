"""여러 기능에서 공유하는 HTTP 입력 검증과 DB 의존성."""

from typing import Annotated

from fastapi import Depends, Path, Request
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.core.security import MAX_BIGINT
from app.db.session import get_db

Database = Annotated[Session, Depends(get_db)]
ResourceId = Annotated[int, Path(gt=0, le=MAX_BIGINT)]


def reject_query_parameters(request: Request) -> None:
    if request.query_params:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "지원하지 않는 조회 조건입니다.",
            [
                {"field": f"query.{key}", "reason": "extra_forbidden"}
                for key in request.query_params
            ],
        )
