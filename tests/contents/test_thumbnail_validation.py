from io import BytesIO

import pytest
from PIL import Image

from app.core.exceptions import ApiError
from app.modules.contents import thumbnail_service


def image_bytes(format="PNG"):
    data = BytesIO()
    with Image.new("RGB", (16, 16), "red") as image:
        image.save(data, format=format)
    return data.getvalue()


@pytest.mark.parametrize(
    "format,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_supported_images_decode(format, mime):
    assert thumbnail_service._validate(image_bytes(format)) == mime


@pytest.mark.parametrize(
    "data",
    [
        b"\x89PNG\r\n\x1a\n",
        b"\xff\xd8\xff",
        b"RIFFxxxxWEBP",
        image_bytes("PNG")[:-12],
        image_bytes("JPEG")[:-20],
    ],
)
def test_broken_images_never_reach_storage(monkeypatch, data):
    def unexpected_write(*args):
        pytest.fail("손상된 이미지를 저장하려고 했습니다.")

    monkeypatch.setattr(thumbnail_service, "_write", unexpected_write)
    with pytest.raises(ApiError) as error:
        thumbnail_service.put_content_thumbnail(None, 1, 1, data)
    assert (error.value.status_code, error.value.code) == (422, "INVALID_IMAGE")


def test_other_image_formats_are_rejected():
    with pytest.raises(ApiError) as error:
        thumbnail_service._validate(image_bytes("GIF"))
    assert error.value.status_code == 415


def test_upload_read_is_bounded(monkeypatch):
    monkeypatch.setattr(thumbnail_service, "MAX_IMAGE_BYTES", 100)
    data = BytesIO(b"x" * 1000)
    with pytest.raises(ApiError) as error:
        thumbnail_service.read_upload(data)
    assert error.value.status_code == 413
    assert data.tell() == 101
    assert thumbnail_service.read_upload(BytesIO(b"x" * 100)) == b"x" * 100
