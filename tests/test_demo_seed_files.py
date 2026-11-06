# 임시 seed 영상·썸네일 복사와 실패 정리 검증. demo_seeds/ 제거 시 함께 제거한다.
import hashlib
import json
import unicodedata
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from PIL import Image

from app.core.config import PROJECT_ROOT
from app.modules.contents.thumbnail_service import MAX_IMAGE_BYTES

demo_injection = pytest.importorskip(
    "demo_seeds.demo_injection",
    reason="데모 전용 검증에는 demo_seeds 폴더를 /app/demo_seeds에 마운트해야 합니다.",
)


@pytest.fixture
def seed_module():
    return demo_injection


@pytest.fixture
def bundle(tmp_path):
    directory = tmp_path / "demo_seeds"
    (directory / "videos").mkdir(parents=True)
    (directory / "thumbnails").mkdir()
    records = []
    for number in (1, 2):
        data = f"file-{number}".encode()
        name = f"엑셀 기초 {number}.mp4"
        (directory / "videos" / name).write_bytes(data)
        image = f"image-{number}".encode()
        image_name = f"엑셀 기초 {number}.jpg"
        (directory / "thumbnails" / image_name).write_bytes(image)
        records.append(
            {
                "storage_path": f"demo/{number}.mp4",
                "video_asset_id": f"00000000-0000-0000-0000-{number:012}",
                "original_name": name,
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "thumbnail": {
                    "storage_path": f"demo/{number}.jpg",
                    "original_name": image_name,
                    "size_bytes": len(image),
                    "sha256": hashlib.sha256(image).hexdigest(),
                },
            }
        )
    sql = "$sasu_demo_data$" + json.dumps({"contents": records}) + "$sasu_demo_data$"
    (directory / "seed.sql").write_text(sql)
    return directory


class FakeEngine:
    def __init__(self, *, sql_error=None, commit_error=None, stored_videos=(), stored_images=()):
        self.connection = Mock()
        self.connection.scalar.return_value = 0
        self.connection.scalars.return_value = []

        def execute(statement, *_args, **_kwargs):
            result = Mock()
            result.mappings.return_value = (
                stored_images if "JOIN sasu.image_assets" in str(statement) else stored_videos
            )
            return result

        self.connection.execute.side_effect = execute
        self.connection.exec_driver_sql.side_effect = sql_error
        self.commit_error = commit_error

    @contextmanager
    def begin(self):
        yield self.connection
        if self.commit_error:
            raise self.commit_error


def test_missing_bundle_video_prevents_insertion(seed_module, bundle, tmp_path):
    (bundle / "videos/엑셀 기초 2.mp4").unlink()
    engine = FakeEngine()
    with pytest.raises(RuntimeError, match="영상이 없거나"):
        seed_module.apply_demo_seed(engine, bundle, tmp_path / "server", tmp_path / "images")
    engine.connection.exec_driver_sql.assert_not_called()


@pytest.mark.parametrize("failure", ["sql", "commit"])
def test_failure_removes_only_new_copies(seed_module, bundle, tmp_path, failure):
    server = tmp_path / "server"
    (server / "demo").mkdir(parents=True)
    (server / "demo/1.mp4").write_bytes(b"file-1")
    images = tmp_path / "images"
    (images / "demo").mkdir(parents=True)
    (images / "demo/1.jpg").write_bytes(b"image-1")
    engine = FakeEngine(**{f"{failure}_error": RuntimeError("failed")})
    with pytest.raises(RuntimeError, match="failed"):
        seed_module.apply_demo_seed(engine, bundle, server, tmp_path / "images")
    assert (server / "demo/1.mp4").read_bytes() == b"file-1"
    assert not (server / "demo/2.mp4").exists()
    assert (images / "demo/1.jpg").read_bytes() == b"image-1"
    assert not (images / "demo/2.jpg").exists()
    assert (bundle / "videos/엑셀 기초 2.mp4").read_bytes() == b"file-2"


def test_existing_different_video_is_not_overwritten(seed_module, bundle, tmp_path):
    server = tmp_path / "server"
    (server / "demo").mkdir(parents=True)
    (server / "demo/2.mp4").write_bytes(b"other-existing-file")
    engine = FakeEngine()
    with pytest.raises(RuntimeError, match="기존 서버 영상과 충돌"):
        seed_module.apply_demo_seed(engine, bundle, server, tmp_path / "images")
    assert not (server / "demo/1.mp4").exists()
    assert (server / "demo/2.mp4").read_bytes() == b"other-existing-file"
    engine.connection.exec_driver_sql.assert_not_called()


def test_repeat_reuses_identical_server_copies(seed_module, bundle, tmp_path):
    server = tmp_path / "server"
    engine = FakeEngine()
    assert seed_module.apply_demo_seed(engine, bundle, server, tmp_path / "images") == (2, 2)
    assert seed_module.apply_demo_seed(engine, bundle, server, tmp_path / "images") == (0, 0)
    assert (server / "demo/1.mp4").read_bytes() == b"file-1"
    assert (server / "demo/2.mp4").read_bytes() == b"file-2"
    assert (tmp_path / "images/demo/1.jpg").read_bytes() == b"image-1"
    assert (tmp_path / "images/demo/2.jpg").read_bytes() == b"image-2"


def test_korean_original_names_work_with_decomposed_filesystem_names(seed_module, bundle, tmp_path):
    original = bundle / "videos/엑셀 기초 1.mp4"
    original.rename(original.with_name(unicodedata.normalize("NFD", original.name)))
    original_image = bundle / "thumbnails/엑셀 기초 1.jpg"
    original_image.rename(
        original_image.with_name(unicodedata.normalize("NFD", original_image.name))
    )
    assert seed_module.apply_demo_seed(
        FakeEngine(), bundle, tmp_path / "server", tmp_path / "images"
    ) == (2, 2)


def test_already_applied_seed_does_not_require_bundle_or_replace_server_files(
    seed_module, bundle, tmp_path
):
    for path in (bundle / "videos").glob("*.mp4"):
        path.unlink()
    for path in (bundle / "thumbnails").glob("*.jpg"):
        path.unlink()
    server = tmp_path / "server"
    server.mkdir()
    replacement = server / "replacement.mp4"
    replacement.write_bytes(b"edited video")
    engine = FakeEngine(
        stored_videos=[
            {"content_id": 12, "storage_path": "replacement.mp4", "size_bytes": 12},
        ]
    )
    engine.connection.scalar.return_value = 2
    assert seed_module.apply_demo_seed(engine, bundle, server, tmp_path / "images") == (0, 0)
    engine.connection.exec_driver_sql.assert_called_once()
    assert replacement.read_bytes() == b"edited video"
    assert list(server.iterdir()) == [replacement]


@pytest.mark.parametrize("state", ["missing", "directory", "wrong_size", "outside_root"])
def test_existing_database_does_not_hide_invalid_server_files(seed_module, bundle, tmp_path, state):
    server = tmp_path / "server"
    server.mkdir()
    relative = "current.mp4"
    if state == "directory":
        (server / relative).mkdir()
    elif state == "wrong_size":
        (server / relative).write_bytes(b"short")
    elif state == "outside_root":
        relative = "../outside.mp4"
        (tmp_path / "outside.mp4").write_bytes(b"edited video")
    engine = FakeEngine(
        stored_videos=[
            {"content_id": 12, "storage_path": relative, "size_bytes": 12},
        ]
    )
    engine.connection.scalar.return_value = 2
    with pytest.raises(RuntimeError, match="서버 영상 확인 실패.*") as error:
        seed_module.apply_demo_seed(engine, bundle, server, tmp_path / "images")
    assert f"콘텐츠 12 / {relative}" in str(error.value)
    if state == "wrong_size":
        assert (server / relative).read_bytes() == b"short"
    assert not (server / "demo").exists()


def test_missing_server_video_exits_without_success_message(
    seed_module, bundle, tmp_path, monkeypatch, capsys
):
    engine = FakeEngine(
        stored_videos=[
            {"content_id": 12, "storage_path": "missing.mp4", "size_bytes": 12},
        ]
    )
    engine.connection.scalar.return_value = 2
    monkeypatch.setattr(seed_module, "BUNDLE_ROOT", bundle)
    monkeypatch.setattr(seed_module, "get_engine", lambda: engine)
    monkeypatch.setattr(
        seed_module,
        "get_settings",
        lambda: Mock(
            video_storage_root=tmp_path / "server", image_storage_root=tmp_path / "images"
        ),
    )
    close = Mock()
    monkeypatch.setattr(seed_module, "close_database", close)
    with pytest.raises(SystemExit, match="데모 seed 처리 중단") as error:
        seed_module.main()
    assert "missing.mp4" in str(error.value)
    assert "데모 seed 처리 완료" not in capsys.readouterr().out
    close.assert_called_once()


@pytest.mark.parametrize("state", ["missing", "wrong_hash"])
def test_invalid_bundle_thumbnail_prevents_any_copy(seed_module, bundle, tmp_path, state):
    image = bundle / "thumbnails/엑셀 기초 2.jpg"
    if state == "missing":
        image.unlink()
    else:
        image.write_bytes(b"changed")
    engine = FakeEngine()
    with pytest.raises(RuntimeError, match="썸네일이 없거나"):
        seed_module.apply_demo_seed(engine, bundle, tmp_path / "server", tmp_path / "images")
    assert not list((tmp_path / "server").rglob("*.mp4"))
    assert not list((tmp_path / "images").rglob("*.jpg"))
    engine.connection.exec_driver_sql.assert_not_called()


def test_image_conflict_keeps_existing_image_and_removes_new_video_copies(
    seed_module, bundle, tmp_path
):
    images = tmp_path / "images"
    (images / "demo").mkdir(parents=True)
    (images / "demo/2.jpg").write_bytes(b"manual image")
    engine = FakeEngine()
    with pytest.raises(RuntimeError, match="기존 서버 썸네일과 충돌"):
        seed_module.apply_demo_seed(engine, bundle, tmp_path / "server", images)
    assert not list((tmp_path / "server").rglob("*.mp4"))
    assert not (images / "demo/1.jpg").exists()
    assert (images / "demo/2.jpg").read_bytes() == b"manual image"
    engine.connection.exec_driver_sql.assert_not_called()


def test_existing_demo_copies_only_missing_thumbnail(seed_module, bundle, tmp_path):
    engine = FakeEngine()
    engine.connection.scalar.return_value = 2
    engine.connection.scalars.return_value = ["00000000-0000-0000-0000-000000000001"]
    for path in (bundle / "videos").glob("*.mp4"):
        path.unlink()
    (bundle / "thumbnails/엑셀 기초 2.jpg").unlink()
    images = tmp_path / "images"
    assert seed_module.apply_demo_seed(engine, bundle, tmp_path / "server", images) == (0, 1)
    assert (images / "demo/1.jpg").read_bytes() == b"image-1"
    assert not (images / "demo/2.jpg").exists()


@pytest.mark.parametrize("state", ["missing", "wrong_size", "outside_root"])
def test_invalid_stored_thumbnail_is_not_reported_as_success(seed_module, bundle, tmp_path, state):
    images = tmp_path / "images"
    images.mkdir()
    relative = "../outside.jpg" if state == "outside_root" else "manual.jpg"
    if state != "missing":
        (images / relative).write_bytes(b"short")
    engine = FakeEngine(
        stored_images=[
            {"content_id": 5, "storage_path": relative, "size_bytes": 7},
        ]
    )
    engine.connection.scalar.return_value = 2
    with pytest.raises(RuntimeError, match="서버 썸네일 확인 실패: 콘텐츠 5"):
        seed_module.apply_demo_seed(engine, bundle, tmp_path / "server", images)


def test_bundled_videos_have_valid_matching_thumbnails_and_seed_metadata():
    bundle = PROJECT_ROOT / "demo_seeds"
    videos = list((bundle / "videos").glob("*.mp4"))
    images = {
        unicodedata.normalize("NFC", path.stem): path
        for path in (bundle / "thumbnails").glob("*.jpg")
    }
    assert videos
    assert {unicodedata.normalize("NFC", path.stem) for path in videos} == images.keys()
    for path in images.values():
        assert 0 < path.stat().st_size <= MAX_IMAGE_BYTES
        with Image.open(path) as image:
            assert image.format == "JPEG"
            image.verify()
        with Image.open(path) as image:
            image.load()
    data = json.loads((bundle / "seed.sql").read_text().split("$sasu_demo_data$")[1])
    for item in data["contents"]:
        thumbnail = item["thumbnail"]
        name = unicodedata.normalize("NFC", item["original_name"].removesuffix(".mp4"))
        assert thumbnail["original_name"] == name + ".jpg"
        assert images[name].stat().st_size == thumbnail["size_bytes"]
        assert demo_injection.file_digest(images[name]) == thumbnail["sha256"]
