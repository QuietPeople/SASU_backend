from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


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
    """서비스의 업무 오류를 HTTP 응답으로 전달한다."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        fields: list[dict[str, str]] | None = None,
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


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    malformed_json = any(error["type"] == "json_invalid" for error in exc.errors())
    return JSONResponse(
        status_code=400 if malformed_json else 422,
        content={
            "detail": {
                "code": "INVALID_REQUEST" if malformed_json else "VALIDATION_ERROR",
                "message": "JSON 구문이 올바르지 않습니다."
                if malformed_json
                else "입력을 확인해 주세요.",
                "fields": [
                    {"field": ".".join(map(str, error["loc"])), "reason": error["msg"]}
                    for error in exc.errors()
                ],
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(ApiError, api_error_handler)
