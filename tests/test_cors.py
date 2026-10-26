import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import main
from app.api.cors import ConfiguredCORSMiddleware
from app.core.config import Settings
from app.core.exceptions import ApiError, register_exception_handlers


def make_client():
    app = FastAPI()
    app.add_middleware(ConfiguredCORSMiddleware)
    register_exception_handlers(app)

    @app.get("/ok")
    def ok():
        return {"ok": True}

    @app.get("/error")
    def error():
        raise ApiError(404, "USER_NOT_FOUND", "사용자 없음")

    return TestClient(app)


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_preflight_accepts_actual_frontend_methods_and_headers(origin, method):
    with make_client() as client:
        response = client.options(
            "/ok",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": (
                    "X-Actor-Id,X-Record-Generation,Content-Type,Range"
                ),
            },
        )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == origin
    assert method in response.headers["Access-Control-Allow-Methods"]
    allowed = response.headers["Access-Control-Allow-Headers"].lower()
    assert all(
        header in allowed for header in ("x-actor-id", "x-record-generation", "content-type")
    )


@pytest.mark.parametrize(
    "override",
    [
        {"Origin": "https://untrusted.example"},
        {"Access-Control-Request-Method": "TRACE"},
        {"Access-Control-Request-Headers": "X-Unknown"},
    ],
)
def test_preflight_rejects_unconfigured_requests(override):
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "X-Actor-Id",
    }
    with make_client() as client:
        response = client.options("/ok", headers=headers | override)
    assert response.status_code == 400
    if "Origin" in override:
        assert "Access-Control-Allow-Origin" not in response.headers


@pytest.mark.parametrize(("path", "status"), [("/ok", 200), ("/error", 404)])
def test_actual_responses_include_cors_headers(path, status):
    with make_client() as client:
        response = client.get(path, headers={"Origin": "http://localhost:5173", "X-Actor-Id": "1"})
        forbidden = client.get(path, headers={"Origin": "https://untrusted.example"})
    assert response.status_code == status
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "Content-Range" in response.headers["Access-Control-Expose-Headers"]
    assert "Access-Control-Allow-Origin" not in forbidden.headers


def test_main_app_uses_cors_and_registers_feed_without_generation_header(monkeypatch):
    monkeypatch.setattr(main, "check_database_connection", lambda: None)
    monkeypatch.setattr(main, "close_database", lambda: None)
    with TestClient(main.app) as client:
        # 실제 개발 DB에 접속하지 않고 앱의 미들웨어·OpenAPI 연결을 확인한다.
        schema = client.get("/openapi.json", headers={"Origin": "http://localhost:5173"})
    assert schema.status_code == 200
    assert schema.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    operation = schema.json()["paths"]["/api/users/{user_id}/feed"]["get"]
    assert operation["operationId"] == "API-CNT-01"
    parameters = {item["name"]: item for item in operation["parameters"]}
    assert parameters["X-Actor-Id"]["required"] is True
    assert "X-Record-Generation" not in parameters


def test_json_env_origin_configuration_is_used(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["https://sasu.example","https://sasu.example"]')
    assert Settings().cors_origins == ["https://sasu.example"]
    with make_client() as client:
        response = client.get("/ok", headers={"Origin": "https://sasu.example"})
        old = client.get("/ok", headers={"Origin": "http://localhost:5173"})
    assert response.headers["Access-Control-Allow-Origin"] == "https://sasu.example"
    assert "Access-Control-Allow-Origin" not in old.headers


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "http://*.example",
        "ftp://example",
        "http://example/path",
        "http://example?key=value",
        "http://example#hash",
        "http://user:pass@example",
        "http://example:70000",
        "http://bad host",
    ],
)
def test_invalid_origin_is_rejected(origin):
    with pytest.raises(ValidationError):
        Settings(cors_origins=[origin])
