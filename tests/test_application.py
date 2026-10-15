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
        assert schema["paths"] == {}

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
