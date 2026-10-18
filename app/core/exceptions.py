"""API 명세의 detail 객체로 오류 응답을 통일한다."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class FieldError(BaseModel):
    field: str
    reason: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    fields: list[FieldError] | None = None


class ErrorResponse(BaseModel):
    detail: ErrorDetail


class ApiError(Exception):
    """서비스의 업무 오류. 기존 fields 위치 인자와 영상 응답 headers를 함께 지원한다."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        fields: list[dict[str, str]] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields
        self.headers = headers


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    detail = {"code": exc.code, "message": exc.message}
    if exc.fields is not None:
        detail["fields"] = exc.fields
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
        headers=exc.headers,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    malformed_json = any(error["type"] == "json_invalid" for error in errors)
    return JSONResponse(
        status_code=400 if malformed_json else 422,
        content={
            "detail": {
                "code": "INVALID_REQUEST" if malformed_json else "VALIDATION_ERROR",
                "message": "요청 형식을 확인해 주세요.",
                "fields": [
                    {
                        "field": ".".join(str(part) for part in error["loc"]),
                        "reason": error["type"],
                    }
                    for error in errors
                ],
            }
        },
    )


async def internal_error_handler(request: Request, exc: Exception):
    # SQL·바인딩 값·접속 정보가 오류 응답과 로그에 포함되지 않게 한다.
    logger.error("Request processing failed: %s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": {"code": "INTERNAL_ERROR", "message": "처리에 실패했습니다."}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(SQLAlchemyError, internal_error_handler)
    app.add_exception_handler(Exception, internal_error_handler)
