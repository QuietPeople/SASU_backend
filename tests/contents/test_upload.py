from decimal import Decimal
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import load_models
from app.db.session import get_db
from app.integrations import ffmpeg
from app.integrations.storage import LocalVideoStorage
from app.modules.categories.models import Category
from app.modules.contents import repository
from app.modules.contents.models import Content, ContentTag, VideoAsset
from app.modules.tags.models import Tag
from app.modules.users.models import User, UserRole
from app.modules.videos import service as video_processing
from app.modules.videos.errors import ProbeTimeout, ProcessingFailed
from app.modules.videos.policy import VideoPolicy
from app.modules.videos.service import VideoIngestService, get_video_ingest_service

# 파일 시그니처 판별(MP4 계열)은 통과하고 ffprobe 단계까지 가는 최소 입력
ISO_BMFF_HEAD = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64


@pytest.fixture
def upload_context(monkeypatch, stub_video_ingest):
    load_models()
    engine = create_engine(
        "sqlite+pysqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"sasu": None}},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session, session.begin():
        admin = User(username="admin", display_name="관리자", role=UserRole.ADMIN)
        learner = User(username="learner", display_name="학습자", role=UserRole.LEARNER)
        category = Category(name="분" * 80)
        tag = Tag(name="태" * 80)
        session.add_all([admin, learner, category, tag])
        session.flush()
        ids = {
            "admin": admin.user_id,
            "learner": learner.user_id,
            "category": category.category_id,
            "tag": tag.tag_id,
        }

    def provide_session():
        with factory() as session:
            yield session

    monkeypatch.setitem(main.app.dependency_overrides, get_db, provide_session)
    monkeypatch.setitem(
        main.app.dependency_overrides, get_video_ingest_service, stub_video_ingest
    )
    client = TestClient(main.app)
    try:
        yield client, factory, ids
    finally:
        client.close()
        engine.dispose()


def create_draft(client, actor_id, data=None):
    response = client.post("/api/contents", json=data or {}, headers={"X-Actor-Id": str(actor_id)})
    assert response.status_code == 201, response.text
    return response.json()["detail"]["content"]["content_id"]


def upload(client, actor_id, content_id, data=b"file-bytes-without-parser"):
    return client.put(
        f"/api/contents/{content_id}/video",
        headers={"X-Actor-Id": str(actor_id)},
        files={"file": ("../../client-name.mp4", data, "application/octet-stream")},
    )


def test_create_metadata_and_upload_persist_correctly(upload_context):
    client, factory, ids = upload_context
    content_id = create_draft(
        client,
        ids["admin"],
        {
            "title": "  최초 등록  ",
            "category_id": ids["category"],
            "tag_ids": [ids["tag"], ids["tag"]],
            "core_content": "첫 문장입니다. 두 번째 문장입니다.",
        },
    )
    response = upload(client, ids["admin"], content_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["video_duration"] == 12.345
    assert body["status"] == "DRAFT"
    assert "preview=true" in body["video_url"]
    assert "video_path" not in body
    with factory() as session:
        content = session.get(Content, content_id)
        assert content.title == "최초 등록"
        assert content.created_by_user_id == ids["admin"]
        asset = session.get(VideoAsset, content.video_asset_id)
        assert asset is not None
        assert body["media_revision"] == str(asset.video_asset_id)
        assert asset.duration_seconds == Decimal("12.345")
        assert asset.mime_type == "video/mp4"
        assert asset.original_name == "client-name.mp4"
        assert asset.size_bytes == len(b"file-bytes-without-parser")
        assert "/" not in asset.storage_path
        assert session.scalar(select(func.count()).select_from(ContentTag)) == 1
        path = get_settings().video_storage_root / asset.storage_path
        assert path.read_bytes() == b"file-bytes-without-parser"


def test_schema_lengths_match_final_database(upload_context):
    client, factory, ids = upload_context
    response = client.post(
        "/api/contents",
        json={"title": "제" * 200, "category_id": ids["category"], "tag_ids": [ids["tag"]]},
        headers={"X-Actor-Id": str(ids["admin"])},
    )
    assert response.status_code == 201, response.text
    content = response.json()["detail"]["content"]
    assert len(content["title"]) == 200
    assert len(content["category"]["name"]) == 80
    assert len(content["tags"][0]["name"]) == 80
    assert content["view_count"] == content["like_count"] == 0


def test_empty_draft_response_reports_missing_fields(upload_context):
    client, factory, ids = upload_context
    response = client.post("/api/contents", json={}, headers={"X-Actor-Id": str(ids["admin"])})
    assert response.status_code == 201
    body = response.json()
    assert body["detail"]["content"]["video_url"] is None
    assert body["detail"]["content"]["status"] == "DRAFT"
    assert set(body["missing_for_publish"]) == {
        "video",
        "title",
        "category_id",
        "tag_ids",
        "core_content",
        "source",
        "reviewed_on",
    }


@pytest.mark.parametrize("actor", ["learner", "missing"])
def test_actor_checks_prevent_database_and_file_writes(upload_context, stored_files, actor):
    client, factory, ids = upload_context
    actor_id = ids["learner"] if actor == "learner" else 999
    expected = 403 if actor == "learner" else 404
    response = client.post("/api/contents", json={}, headers={"X-Actor-Id": str(actor_id)})
    assert response.status_code == expected
    content_id = create_draft(client, ids["admin"])
    assert upload(client, actor_id, content_id).status_code == expected
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Content)) == 1
        assert session.get(Content, content_id).video_asset_id is None
    assert stored_files() == []


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"category_id": 999}, "CATEGORY_NOT_FOUND"),
        ({"tag_ids": [999]}, "TAG_NOT_FOUND"),
    ],
)
def test_missing_references_cancel_creation(upload_context, payload, code):
    client, factory, ids = upload_context
    response = client.post("/api/contents", json=payload, headers={"X-Actor-Id": str(ids["admin"])})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == code
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Content)) == 0


def test_second_upload_keeps_original_file(upload_context, stored_files):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    first = upload(client, ids["admin"], content_id, b"first")
    second = upload(client, ids["admin"], content_id, b"second")
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "VIDEO_ALREADY_EXISTS"
    files = stored_files()
    assert len(files) == 1
    assert files[0].read_bytes() == b"first"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(VideoAsset)) == 1


def test_empty_upload_leaves_no_files(upload_context, stored_files):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    response = upload(client, ids["admin"], content_id, b"")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "EMPTY_UPLOAD"
    assert stored_files() == []
    with factory() as session:
        assert session.get(Content, content_id).video_asset_id is None
        assert session.scalar(select(func.count()).select_from(VideoAsset)) == 0


def test_missing_processing_tool_does_not_write_files_or_assets(
    upload_context, monkeypatch, stored_files
):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    monkeypatch.delitem(main.app.dependency_overrides, get_video_ingest_service)
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda name: None)
    response = upload(client, ids["admin"], content_id, ISO_BMFF_HEAD)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "VIDEO_PROCESSING_UNAVAILABLE"
    assert stored_files() == []
    with factory() as session:
        assert session.get(Content, content_id).video_asset_id is None
        assert session.scalar(select(func.count()).select_from(VideoAsset)) == 0


def test_conversion_failure_does_not_write_files_or_assets(
    upload_context, monkeypatch, video_samples, stored_files
):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    monkeypatch.delitem(main.app.dependency_overrides, get_video_ingest_service)

    def broken_remux(*args, **kwargs):
        raise ProcessingFailed("영상을 저장 형식으로 변환하지 못했습니다.")

    monkeypatch.setattr(video_processing, "remux", broken_remux)
    response = upload(client, ids["admin"], content_id, video_samples["mp4"].read_bytes())
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "VIDEO_PROCESSING_FAILED"
    assert stored_files() == []
    with factory() as session:
        assert session.get(Content, content_id).video_asset_id is None
        assert session.scalar(select(func.count()).select_from(VideoAsset)) == 0


@pytest.mark.parametrize("failure_point", ["flush", "commit"])
def test_database_failure_rolls_back_and_removes_new_file(
    upload_context, monkeypatch, stored_files, failure_point
):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])

    def fail(*args, **kwargs):
        raise SQLAlchemyError("simulated persistence failure")

    if failure_point == "flush":
        monkeypatch.setattr(repository, "attach_video", fail)
    else:
        event.listen(Session, "before_commit", fail)
    try:
        response = upload(client, ids["admin"], content_id)
    finally:
        if failure_point == "commit":
            event.remove(Session, "before_commit", fail)
    assert response.status_code == 500
    assert "simulated" not in response.text
    assert stored_files() == []
    with factory() as session:
        assert session.get(Content, content_id).video_asset_id is None
        assert session.scalar(select(func.count()).select_from(VideoAsset)) == 0


def test_unknown_content_does_not_create_file(upload_context, stored_files):
    client, factory, ids = upload_context
    assert upload(client, ids["admin"], 999).status_code == 404
    assert stored_files() == []


def test_interrupted_file_copy_cleans_temporary_file(tmp_path):
    class BrokenStream(BytesIO):
        def read(self, size):
            raise OSError("interrupted input")

    service = VideoIngestService(LocalVideoStorage(tmp_path), VideoPolicy())
    with pytest.raises(OSError, match="interrupted"):
        service.ingest(BrokenStream(b"data"), "a.mp4")
    assert list(tmp_path.iterdir()) == []


def test_real_video_upload_is_processed_and_stored(upload_context, monkeypatch, video_samples):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    monkeypatch.delitem(main.app.dependency_overrides, get_video_ingest_service)
    original = video_samples["mp4"].read_bytes()
    # filename과 Content-Type 대신 실제 파일 내용으로 검사해야 한다.
    response = client.put(
        f"/api/contents/{content_id}/video",
        headers={"X-Actor-Id": str(ids["admin"])},
        files={"file": ("renamed.bin", original, "text/plain")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["video_duration"] == 1.2
    with factory() as session:
        content = session.get(Content, content_id)
        asset = session.get(VideoAsset, content.video_asset_id)
        assert asset.mime_type == "video/mp4"
        assert asset.duration_seconds == Decimal("1.200")
        assert asset.original_name == "renamed.bin"
        assert asset.storage_path == f"{asset.video_asset_id.hex}.mp4"
        stored = get_settings().video_storage_root / asset.storage_path
        # 웹 재생용으로 정규화(faststart)된 파일이 저장되고, 크기는 저장본 기준이다.
        assert asset.size_bytes == stored.stat().st_size
        data = stored.read_bytes()
        assert 0 <= data.find(b"moov") < data.find(b"mdat")


@pytest.mark.parametrize("sample", ["mov", "matroska", "faststart", "fragmented"])
def test_h264_containers_are_converted_to_mp4(upload_context, monkeypatch, video_samples, sample):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    monkeypatch.delitem(main.app.dependency_overrides, get_video_ingest_service)
    response = upload(client, ids["admin"], content_id, video_samples[sample].read_bytes())
    assert response.status_code == 200, response.text
    with factory() as session:
        asset = session.get(VideoAsset, session.get(Content, content_id).video_asset_id)
        assert asset.mime_type == "video/mp4" and asset.storage_path.endswith(".mp4")


@pytest.mark.parametrize(
    "sample,status,code",
    [
        ("fake", 415, "UNSUPPORTED_MEDIA_TYPE"),
        ("empty", 422, "EMPTY_UPLOAD"),
        ("truncated", 422, "INVALID_VIDEO"),
        ("audio", 415, "UNSUPPORTED_MEDIA_TYPE"),
    ],
)
def test_real_invalid_video_does_not_persist(
    upload_context, monkeypatch, video_samples, stored_files, sample, status, code
):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    monkeypatch.delitem(main.app.dependency_overrides, get_video_ingest_service)
    response = upload(client, ids["admin"], content_id, video_samples[sample].read_bytes())
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code
    assert response.json()["detail"]["fields"][0]["field"] == "file"
    assert stored_files() == []
    with factory() as session:
        assert session.get(Content, content_id).video_asset_id is None
        assert session.scalar(select(func.count()).select_from(VideoAsset)) == 0


def test_video_inspection_timeout_does_not_persist(
    upload_context, monkeypatch, video_samples, stored_files
):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    monkeypatch.delitem(main.app.dependency_overrides, get_video_ingest_service)

    def timed_out(*args, **kwargs):
        raise ProbeTimeout("영상 검사 제한 시간을 초과했습니다.")

    monkeypatch.setattr(video_processing, "probe", timed_out)
    response = upload(client, ids["admin"], content_id, video_samples["mp4"].read_bytes())
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VIDEO_INSPECTION_TIMEOUT"
    assert stored_files() == []
    with factory() as session:
        assert session.get(Content, content_id).video_asset_id is None
        assert session.scalar(select(func.count()).select_from(VideoAsset)) == 0


def test_oversized_request_is_rejected_before_processing(upload_context, monkeypatch, stored_files):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    monkeypatch.setenv("VIDEO_MAX_MB", "1")
    get_settings.cache_clear()
    monkeypatch.delitem(main.app.dependency_overrides, get_video_ingest_service)
    response = upload(client, ids["admin"], content_id, b"\x00" * (3 * 1024 * 1024))
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "FILE_TOO_LARGE"
    assert stored_files() == []


def test_video_policy_reports_upload_limits(upload_context):
    client, factory, ids = upload_context
    response = client.get("/api/contents/video-policy")
    assert response.status_code == 200
    body = response.json()
    assert body["max_bytes"] == 200 * 1024 * 1024
    assert (body["min_duration_sec"], body["max_duration_sec"]) == (1.0, 180.0)
    assert ".mp4" in body["accept"]
