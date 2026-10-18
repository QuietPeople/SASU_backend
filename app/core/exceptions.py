"""공통 예외와 FastAPI 예외 핸들러.

오류 응답 형식(SASU API 명세서 1.1):

    {"error": {"code": "PUBLISH_REQUIRED_MISSING", "message": "...", "fields": ["tags"]}}

AppError는 FastAPI 없이도 import할 수 있게 두고(영상 처리 단독 테스트용),
핸들러 등록에 필요한 FastAPI 모듈은 register_exception_handlers 안에서 불러온다.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


class AppError(Exception):
    """서비스에서 발생시키는 업무 오류. 핸들러가 공통 형식으로 응답한다."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        fields: list[str] | None = None,
        detail: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields
        self.detail = detail


def not_found(what: str = "대상") -> AppError:
    return AppError(404, "NOT_FOUND", f"{what}을(를) 찾을 수 없습니다.")


def invalid_request(message: str, *fields: str) -> AppError:
    return AppError(400, "INVALID_REQUEST", message, fields=list(fields) or None)


def error_body(
    code: str, message: str, fields: list[str] | None = None, detail: dict | None = None
) -> dict:
    error: dict = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    if detail:
        error["detail"] = detail
    return {"error": error}


def register_exception_handlers(app: "FastAPI") -> None:
    from fastapi import Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException

    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("%s: %s", exc.code, exc.message)
        body = error_body(exc.code, exc.message, exc.fields, exc.detail)
        return JSONResponse(body, status_code=exc.status_code)

    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({str(err["loc"][-1]) for err in exc.errors() if err.get("loc")})
        body = error_body("INVALID_REQUEST", "요청 형식이 올바르지 않습니다.", fields)
        return JSONResponse(body, status_code=400)

    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(error_body(code, str(exc.detail)), status_code=exc.status_code)

    app.add_exception_handler(AppError, app_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(StarletteHTTPException, http_error)
