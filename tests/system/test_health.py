"""정상·의존 자원 장애·저장소 검사 후 파일 정리를 실제 HTTP 응답으로 검증한다."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import main
from app.core.config import get_settings
from app.integrations import storage
from app.modules.system import service


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "check_database_connection", lambda: None)
    monkeypatch.setattr(service, "check_database_connection", lambda: None)
    with TestClient(main.app) as http:
        yield http


def test_healthy_without_actor_header_preserves_existing_files(client):
    root = get_settings().video_storage_root
    video = root / "existing.mp4"
    video.write_bytes(b"existing video bytes")
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "video_storage": "ok"}
    assert response.headers["cache-control"] == "no-store"
    assert list(root.iterdir()) == [video]
    assert video.read_bytes() == b"existing video bytes"


@pytest.mark.parametrize(
    ("database_down", "storage_down"), [(True, False), (False, True), (True, True)]
)
def test_dependency_failures_report_all_statuses_without_secrets(
    client, monkeypatch, database_down, storage_down
):
    if database_down:

        def unavailable_database():
            raise OperationalError("private SQL", {}, Exception("private DB password"))

        monkeypatch.setattr(service, "check_database_connection", unavailable_database)
    if storage_down:
        get_settings().video_storage_root.rmdir()
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "unavailable" if database_down else "ok",
        "video_storage": "unavailable" if storage_down else "ok",
        "detail": {
            "code": "SERVICE_UNAVAILABLE",
            "message": "DB 또는 영상 저장소가 준비되지 않았습니다.",
        },
    }
    assert response.headers["cache-control"] == "no-store"
    assert "private" not in response.text
    assert str(get_settings().video_storage_root) not in response.text
    if storage_down:
        assert not get_settings().video_storage_root.exists()
    else:
        assert list(get_settings().video_storage_root.iterdir()) == []


def test_storage_directory_read_denied(client, monkeypatch):
    def read_denied(_root):
        raise PermissionError("private storage directory")

    monkeypatch.setattr(storage, "scandir", read_denied)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["video_storage"] == "unavailable"
    assert "private" not in response.text


def test_storage_write_denied(client, monkeypatch):
    def write_denied(**_kwargs):
        raise PermissionError("private storage directory")

    monkeypatch.setattr(storage, "TemporaryFile", write_denied)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["database"] == "ok"
    assert response.json()["video_storage"] == "unavailable"
    assert "private" not in response.text


def test_file_instead_of_storage_directory_is_unavailable(client):
    root = get_settings().video_storage_root
    root.rmdir()
    root.write_bytes(b"existing file")
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["video_storage"] == "unavailable"
    assert root.read_bytes() == b"existing file"


def test_unexpected_query_is_rejected(client):
    response = client.get("/api/health?unknown=1")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"
