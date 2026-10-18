import pytest
from fastapi.testclient import TestClient

from app import main
from app.db.session import get_db
from app.modules.contents.schemas import ContentUpdate


@pytest.fixture
def client(monkeypatch):
    def unexpected_database_access():
        pytest.fail("콘텐츠 API 계약 검증에서 DB를 사용하면 안 됩니다.")

    monkeypatch.setattr(main, "check_database_connection", unexpected_database_access)
    # 입출력 오류는 DB 연결 없이 검증한다. 쓰기 성공 경로는 test_upload에서 검증한다.
    monkeypatch.setitem(main.app.dependency_overrides, get_db, lambda: None)
    # lifespan은 실행하지 않는다. DB를 사용하는 기존 앱 시작 정책과 계약 검증을 분리한다.
    instance = TestClient(main.app)
    try:
        yield instance
    finally:
        instance.close()


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("GET", "/api/contents?page=0", {}),
        ("GET", "/api/contents?size=101", {}),
        ("GET", "/api/contents?unknown=value", {}),
        ("GET", "/api/contents/0", {}),
        ("POST", "/api/contents", {"json": {"video_path": "arbitrary.mp4"}}),
        ("POST", "/api/contents", {"json": {"caution_enabled": True}}),
        ("PATCH", "/api/contents/1", {"json": {}}),
        ("PATCH", "/api/contents/1", {"json": {"tag_ids": None}}),
        ("PATCH", "/api/contents/1", {"json": {"caution_enabled": None}}),
        ("PUT", "/api/contents/1/video", {"json": {"file": "not-a-file"}}),
        ("GET", "/api/contents/1/video?preview=true", {}),
        ("GET", "/api/contents/1/video?preview=true&actor_id=3", {}),
    ],
)
def test_invalid_contracts_have_structured_errors(client, method, path, kwargs):
    response = client.request(method, path, headers={"X-Actor-Id": "2"}, **kwargs)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_actor_header_requirement_and_preview_actor_validation(client):
    assert client.get("/api/contents").status_code == 422
    assert client.get("/api/contents/1/video?preview=true").status_code == 422


def test_patch_preserves_omitted_fields_and_explicit_clears():
    patch = ContentUpdate(title="  수정 제목  ")
    assert patch.model_dump(exclude_unset=True) == {"title": "수정 제목"}
    patch = ContentUpdate(source=None, tag_ids=[], caution_enabled=False)
    assert patch.model_dump(exclude_unset=True) == {
        "source": None,
        "tag_ids": [],
        "caution_enabled": False,
    }


def test_malformed_json_is_distinct_from_field_validation(client):
    response = client.post(
        "/api/contents",
        content="{",
        headers={"X-Actor-Id": "2", "Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_REQUEST"


def test_multipart_rejects_extra_fields_and_multiple_files(client):
    headers = {"X-Actor-Id": "2"}
    file = ("sample.mp4", b"contract-only", "video/mp4")
    for kwargs in (
        {"files": {"file": file}, "data": {"video_path": "arbitrary.mp4"}},
        {"files": [("file", file), ("file", file)]},
        {
            "files": [
                ("file", file),
                ("expected_media_revision", (None, "first")),
                ("expected_media_revision", (None, "second")),
            ]
        },
    ):
        response = client.put("/api/contents/1/video", headers=headers, **kwargs)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_openapi_distinguishes_json_upload_and_binary_download(client):
    schema = client.get("/openapi.json").json()
    operations = [
        operation
        for route, path in schema["paths"].items()
        if route.startswith("/api/contents")
        for operation in path.values()
    ]
    assert {operation["operationId"] for operation in operations} >= {
        f"API-CNT-{number:02d}" for number in range(2, 9)
    }
    video = schema["paths"]["/api/contents/{content_id}/video"]
    assert "multipart/form-data" in video["put"]["requestBody"]["content"]
    for code in ("200", "206"):
        # 데이터 처리 모듈이 MP4(faststart) 또는 WebM으로 저장한다.
        assert set(video["get"]["responses"][code]["content"]) == {"video/mp4", "video/webm"}
    assert "201" in schema["paths"]["/api/contents"]["post"]["responses"]
