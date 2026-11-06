from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.core.config import get_settings
from app.modules.contents import thumbnail_service
from app.modules.contents.models import Content, ImageAsset, VideoAsset
from app.modules.videos.errors import ThumbnailGenerationFailed
from tests.contents.test_upload import create_draft
from tests.contents.test_upload import upload_context as upload_context


def upload(client, ids, content_id, **data):
    return client.put(
        f"/api/contents/{content_id}/video",
        headers={"X-Actor-Id": str(ids["admin"])},
        files={"file": ("sample.mp4", b"stub-video")},
        data=data,
    )


def image_files():
    root = get_settings().image_storage_root
    return sorted(root.iterdir()) if root.exists() else []


def put_direct(client, ids, content_id):
    data = BytesIO()
    with Image.new("RGB", (20, 30), "red") as image:
        image.save(data, format="PNG")
    response = client.put(
        f"/api/contents/{content_id}/thumbnail",
        headers={"X-Actor-Id": str(ids["admin"])},
        files={"file": ("direct.png", data.getvalue())},
    )
    assert response.status_code == 204, response.text
    return data.getvalue()


def no_extraction(*args):
    pytest.fail("이미지가 있거나 생성을 해제한 요청은 프레임을 추출하면 안 됨")


def test_upload_generates_thumbnail_and_uses_existing_image_api(upload_context):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    response = upload(client, ids, content_id)
    assert response.status_code == 200, response.text
    with factory() as session:
        content = session.get(Content, content_id)
        assert content.video_asset_id is not None
        image = session.get(ImageAsset, content.thumbnail_image_id)
        assert image is not None and image.mime_type == "image/jpeg"
        assert image.size_bytes == image_files()[0].stat().st_size
    # 전체 상세 조회·시리즈 연결은 PostgreSQL 관리자 통합 테스트에서 확인한다.
    image_response = client.get(
        f"/api/contents/{content_id}/thumbnail?preview=true&actor_id={ids['admin']}"
    )
    assert image_response.status_code == 200
    assert image_response.content == image_files()[0].read_bytes()
    assert image_response.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/contents/{content_id}/thumbnail").status_code == 404
    with Image.open(BytesIO(image_response.content)) as image:
        assert image.format == "JPEG" and image.size == (32, 32)


def test_explicit_false_skips_extraction(upload_context, monkeypatch, stub_video_ingest):
    client, factory, ids = upload_context
    monkeypatch.setattr(stub_video_ingest, "extract_thumbnail", no_extraction)
    content_id = create_draft(client, ids["admin"])
    response = upload(client, ids, content_id, generate_thumbnail="false")
    assert response.status_code == 200, response.text
    with factory() as session:
        content = session.get(Content, content_id)
        assert content.video_asset_id is not None
        assert content.thumbnail_image_id is None
        assert session.scalar(select(func.count()).select_from(ImageAsset)) == 0
    assert image_files() == []


@pytest.mark.parametrize("existing", ["direct", "generated"])
def test_existing_thumbnail_is_kept_when_video_is_replaced(
    upload_context, monkeypatch, stub_video_ingest, existing
):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    if existing == "direct":
        put_direct(client, ids, content_id)
        monkeypatch.setattr(stub_video_ingest, "extract_thumbnail", no_extraction)
    first = upload(client, ids, content_id)
    assert first.status_code == 200, first.text
    with factory() as session:
        image_id = session.get(Content, content_id).thumbnail_image_id
    files_before = image_files()
    monkeypatch.setattr(stub_video_ingest, "extract_thumbnail", no_extraction)
    second = upload(client, ids, content_id, expected_media_revision=first.json()["media_revision"])
    assert second.status_code == 200, second.text
    assert second.json()["media_revision"] != first.json()["media_revision"]
    with factory() as session:
        assert session.get(Content, content_id).thumbnail_image_id == image_id
    assert image_files() == files_before


def test_direct_upload_replaces_generated_thumbnail(upload_context):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    assert upload(client, ids, content_id).status_code == 200
    generated_file = image_files()[0]
    with factory() as session:
        old_id = session.get(Content, content_id).thumbnail_image_id
    direct = put_direct(client, ids, content_id)
    assert not generated_file.exists()
    assert len(image_files()) == 1 and image_files()[0].read_bytes() == direct
    with factory() as session:
        assert session.get(Content, content_id).thumbnail_image_id != old_id
        assert session.get(ImageAsset, old_id) is None


def test_direct_image_added_during_processing_wins(upload_context, monkeypatch, stub_video_ingest):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    original = stub_video_ingest.extract_thumbnail

    def interleaved(self, video):
        generated = original(self, video)
        put_direct(client, ids, content_id)
        return generated

    monkeypatch.setattr(stub_video_ingest, "extract_thumbnail", interleaved)
    response = upload(client, ids, content_id)
    assert response.status_code == 200, response.text
    assert len(image_files()) == 1 and image_files()[0].suffix == ".png"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ImageAsset)) == 1
        content = session.get(Content, content_id)
        assert session.get(ImageAsset, content.thumbnail_image_id).mime_type == "image/png"


@pytest.mark.parametrize("replacement", [False, True])
def test_extraction_failure_cleans_new_files_and_preserves_previous_video(
    upload_context, monkeypatch, stub_video_ingest, stored_files, replacement
):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    data = {}
    previous_revision = None
    if replacement:
        first = upload(client, ids, content_id, generate_thumbnail="false")
        assert first.status_code == 200
        previous_revision = first.json()["media_revision"]
        data["expected_media_revision"] = previous_revision
    before = stored_files()

    def failed(*args):
        raise ThumbnailGenerationFailed("첫 프레임 추출 실패")

    monkeypatch.setattr(stub_video_ingest, "extract_thumbnail", failed)
    response = upload(client, ids, content_id, **data)
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "THUMBNAIL_GENERATION_FAILED"
    assert stored_files() == before and image_files() == []
    with factory() as session:
        content = session.get(Content, content_id)
        assert (
            str(content.video_asset_id) if content.video_asset_id else None
        ) == previous_revision
        assert content.thumbnail_image_id is None
        assert session.scalar(select(func.count()).select_from(VideoAsset)) == int(replacement)
        assert session.scalar(select(func.count()).select_from(ImageAsset)) == 0


def test_image_storage_failure_discards_new_video(upload_context, monkeypatch, stored_files):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])

    def failed(*args):
        raise OSError("image storage unavailable")

    monkeypatch.setattr(thumbnail_service, "_write", failed)
    response = upload(client, ids, content_id)
    assert response.status_code == 500
    assert stored_files() == [] and image_files() == []
    with factory() as session:
        assert session.get(Content, content_id).video_asset_id is None
        assert session.scalar(select(func.count()).select_from(ImageAsset)) == 0


def test_invalid_generated_image_is_server_error_and_cleans_video(
    upload_context, monkeypatch, stored_files, stub_video_ingest
):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    monkeypatch.setattr(stub_video_ingest, "extract_thumbnail", lambda *args: b"not-an-image")
    response = upload(client, ids, content_id)
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "THUMBNAIL_GENERATION_FAILED"
    assert stored_files() == [] and image_files() == []


@pytest.mark.parametrize("value", ["invalid", ""])
def test_invalid_generation_flag_is_rejected_before_upload(upload_context, stored_files, value):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    response = upload(client, ids, content_id, generate_thumbnail=value)
    assert response.status_code == 422, response.text
    assert stored_files() == [] and image_files() == []


def test_duplicate_generation_flag_is_rejected(upload_context, stored_files):
    client, factory, ids = upload_context
    content_id = create_draft(client, ids["admin"])
    response = client.put(
        f"/api/contents/{content_id}/video",
        headers={"X-Actor-Id": str(ids["admin"])},
        files=[
            ("file", ("sample.mp4", b"stub-video")),
            ("generate_thumbnail", (None, "true")),
            ("generate_thumbnail", (None, "false")),
        ],
    )
    assert response.status_code == 422
    assert stored_files() == [] and image_files() == []
