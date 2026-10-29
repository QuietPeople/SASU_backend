from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import main
from app.db.session import get_db
from app.modules.contents import service, video_service
from app.modules.contents.schemas import ContentCreate, ContentUpdate


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


@pytest.mark.parametrize(
    ("method", "path"), [("POST", "/api/contents"), ("PATCH", "/api/contents/1")]
)
@pytest.mark.parametrize("field", ["category_id", "tag_ids"])
@pytest.mark.parametrize("value", [True, False, "1", 1.0, 1.5, 0, -1, 2**63])
def test_reference_ids_reject_wrong_types_and_out_of_range_values(
    client, monkeypatch, method, path, field, value
):
    def unexpected_service_call(*args, **kwargs):
        pytest.fail("잘못된 참조 ID는 서비스 호출 전에 거절해야 합니다.")

    monkeypatch.setattr(service, "create_content", unexpected_service_call)
    monkeypatch.setattr(service, "update_content", unexpected_service_call)
    payload = {field: [1, value] if field == "tag_ids" else value}
    response = client.request(method, path, headers={"X-Actor-Id": "2"}, json=payload)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "VALIDATION_ERROR"
    error_field = "body.tag_ids.1" if field == "tag_ids" else "body.category_id"
    assert [error["field"] for error in detail["fields"]] == [error_field]


@pytest.mark.parametrize("model", [ContentCreate, ContentUpdate])
@pytest.mark.parametrize(
    "payload",
    [
        {"category_id": 1, "tag_ids": [1, 2**63 - 1]},
        {"category_id": 2**63 - 1},
        {"category_id": None, "tag_ids": []},
        {"title": "제목만 전달"},
    ],
)
def test_reference_ids_keep_valid_bounds_and_omission_semantics(model, payload):
    assert model.model_validate(payload).model_dump(exclude_unset=True) == payload


@pytest.mark.parametrize(
    ("method", "path"), [("POST", "/api/contents"), ("PATCH", "/api/contents/1")]
)
@pytest.mark.parametrize(
    "value",
    [0, True, "2026-10-29T00:00:00", "20261029", "2026-2-9", "2026-02-30", "0000-01-01"],
)
def test_reviewed_on_rejects_non_date_inputs_before_service(
    client, monkeypatch, method, path, value
):
    def unexpected_service_call(*args, **kwargs):
        pytest.fail("잘못된 검토일은 서비스 호출 전에 거절해야 합니다.")

    monkeypatch.setattr(service, "create_content", unexpected_service_call)
    monkeypatch.setattr(service, "update_content", unexpected_service_call)
    response = client.request(
        method, path, headers={"X-Actor-Id": "2"}, json={"reviewed_on": value}
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "VALIDATION_ERROR"
    assert [error["field"] for error in detail["fields"]] == ["body.reviewed_on"]


@pytest.mark.parametrize("model", [ContentCreate, ContentUpdate])
@pytest.mark.parametrize(
    ("value", "expected"),
    [("2026-10-29", date(2026, 10, 29)), (" 2024-02-29 ", date(2024, 2, 29)), (None, None)],
)
def test_reviewed_on_keeps_calendar_dates_and_null(model, value, expected):
    assert model(reviewed_on=value).reviewed_on == expected


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("GET", "/api/contents/video-policy", {}),
        ("POST", "/api/contents", {"json": {}}),
        ("PATCH", "/api/contents/1", {"json": {"title": "수정"}}),
        (
            "PUT", "/api/contents/1/video",
            {"files": {"file": ("sample.mp4", b"contract-only", "video/mp4")}},
        ),
        ("POST", "/api/contents/1/publish", {}),
    ],
)
def test_content_writes_and_video_policy_reject_unknown_queries_before_service(
    client, monkeypatch, method, path, kwargs
):
    def unexpected_service_call(*args, **kwargs):
        pytest.fail("미정의 Query는 저장·영상 처리 전에 거절해야 합니다.")

    for name in ("create_content", "update_content", "publish_content"):
        monkeypatch.setattr(service, name, unexpected_service_call)
    monkeypatch.setattr(video_service, "upload_video", unexpected_service_call)
    response = client.request(
        method, f"{path}?unknown=value", headers={"X-Actor-Id": "2"}, **kwargs
    )
    assert response.status_code == 422
    assert response.json()["detail"]["fields"] == [
        {"field": "query.unknown", "reason": "extra_forbidden"}
    ]


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


@pytest.mark.parametrize(
    "content_type", ["multipart/form-data", "multipart/form-data; boundary=example-boundary"]
)
def test_malformed_multipart_has_common_error_contract(client, content_type):
    response = client.put(
        "/api/contents/1/video",
        content=b"invalid multipart body",
        headers={"X-Actor-Id": "2", "Content-Type": content_type},
    )
    assert response.status_code == 400
    assert response.json() == {
        "detail": {"code": "INVALID_REQUEST", "message": "요청 형식을 확인해 주세요."}
    }


@pytest.mark.parametrize("path", ["/api/contents", "/api/contents/1/video"])
@pytest.mark.parametrize("value", ["0", "-1", str(2**63), "invalid"])
def test_required_and_optional_actor_headers_keep_id_bounds(client, path, value):
    response = client.get(path, headers={"X-Actor-Id": value})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


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
