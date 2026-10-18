"""실제 개발 DB와 독립적으로 앱 수명주기와 문서 제공을 검증한다."""

import pytest
from fastapi.testclient import TestClient

from app import main


def test_startup_database_check_and_documentation(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(main, "check_database_connection", lambda: calls.append("checked"))
    monkeypatch.setattr(main, "close_database", lambda: calls.append("closed"))

    with TestClient(main.app) as client:
        assert calls == ["checked"]
        assert (tmp_path / "videos").is_dir()
        docs = client.get("/docs")
        assert docs.status_code == 200
        assert "SwaggerUIBundle" in docs.text
        assert client.get("/redoc").status_code == 200
        schema = client.get("/openapi.json").json()
        assert schema["info"]["title"] == "SASU Backend API"
        assert "/api/contents/{content_id}/statistics/reactions" in schema["paths"]
        assert "/api/users/{user_id}/test-records/reset" in schema["paths"]
        assert {"get", "post"} <= schema["paths"]["/api/categories"].keys()
        assert "patch" in schema["paths"]["/api/categories/{category_id}"]
        assert {"get", "post"} <= schema["paths"]["/api/tags"].keys()
        assert {"get", "post"} <= schema["paths"]["/api/contents/{content_id}/question"].keys()
        assert {"get", "post"} <= schema["paths"]["/api/questions/{question_id}/versions"].keys()
        assert {"get", "post"} <= schema["paths"]["/api/curriculums"].keys()
        assert {"get", "patch"} <= schema["paths"]["/api/curriculums/{curriculum_id}"].keys()
        assert {"get", "put"} <= schema["paths"]["/api/curriculums/{curriculum_id}/steps"].keys()
        assert "get" in schema["paths"]["/api/health"]
        assert "get" in schema["paths"]["/api/users"]
        assert "get" in schema["paths"]["/api/users/{user_id}"]
        assert "get" in schema["paths"]["/api/responses/{response_id}"]

    assert calls == ["checked", "closed"]


def test_database_failure_prevents_successful_startup(monkeypatch):
    calls = []

    def fail_connection():
        raise OSError("database unavailable")

    monkeypatch.setattr(main, "check_database_connection", fail_connection)
    monkeypatch.setattr(main, "close_database", lambda: calls.append("closed"))
    with pytest.raises(OSError, match="database unavailable"), TestClient(main.app):
        pass
    assert calls == ["closed"]
