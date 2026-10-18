"""팀원 영상 오류 헤더와 기존 관리자 오류 계약의 HTTP 호환성 검증."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import OperationalError

from app.core.exceptions import ApiError, register_exception_handlers


@pytest.fixture
def error_response():
    def request(error):
        application = FastAPI()
        register_exception_handlers(application)

        @application.get("/error")
        def endpoint():
            raise error

        with TestClient(application, raise_server_exceptions=False) as client:
            return client.get("/error")

    return request


def test_video_range_error_preserves_status_body_and_headers(error_response):
    response = error_response(
        ApiError(
            416,
            "RANGE_NOT_SATISFIABLE",
            "요청한 영상 바이트 범위를 제공할 수 없습니다.",
            headers={
                "Content-Range": "bytes */100",
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-store",
            },
        )
    )
    assert response.status_code == 416
    assert response.json() == {
        "detail": {
            "code": "RANGE_NOT_SATISFIABLE",
            "message": "요청한 영상 바이트 범위를 제공할 수 없습니다.",
        }
    }
    assert response.headers["content-range"] == "bytes */100"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("positional", [True, False])
def test_legacy_and_upload_field_errors_share_the_same_contract(error_response, positional):
    fields = [{"field": "title", "reason": "required_for_publish"}]
    args = (422, "VALIDATION_ERROR", "입력을 확인해 주세요.")
    error = ApiError(*args, fields) if positional else ApiError(*args, fields=fields)
    response = error_response(error)
    assert response.status_code == 422
    assert response.json() == {
        "detail": {"code": "VALIDATION_ERROR", "message": args[2], "fields": fields}
    }


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("private SQL", {}, Exception("secret connection")),
        RuntimeError("secret storage path"),
    ],
)
def test_database_and_unexpected_failures_keep_generic_500_contract(error_response, error):
    response = error_response(error)
    assert response.status_code == 500
    assert response.json() == {
        "detail": {"code": "INTERNAL_ERROR", "message": "처리에 실패했습니다."}
    }
    assert "private" not in response.text and "secret" not in response.text


class ValidatedInput(BaseModel):
    value: str

    @field_validator("value")
    @classmethod
    def reject_value(cls, value):
        raise ValueError(f"private validation message: {value}")


@pytest.mark.parametrize(
    "body,status,code,reason",
    [
        ("{", 400, "INVALID_REQUEST", "json_invalid"),
        ('{"value":"secret input"}', 422, "VALIDATION_ERROR", "value_error"),
    ],
)
def test_validation_preserves_json_status_and_excludes_input(body, status, code, reason):
    application = FastAPI()
    register_exception_handlers(application)

    @application.post("/validate")
    def endpoint(request: ValidatedInput):
        return request

    with TestClient(application) as client:
        response = client.post(
            "/validate", content=body, headers={"Content-Type": "application/json"}
        )
    assert response.status_code == status
    detail = response.json()["detail"]
    assert detail["code"] == code
    assert detail["fields"][0]["reason"] == reason
    assert "private" not in response.text and "secret" not in response.text
