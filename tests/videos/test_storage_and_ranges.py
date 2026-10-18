"""로컬 저장소 경로 검사와 HTTP Range 해석을 검증한다."""

import pytest

from app.integrations.storage import LocalVideoStorage, StoragePathError
from app.modules.videos.errors import RangeNotSatisfiable
from app.modules.videos.streaming import iter_file, parse_range


@pytest.fixture
def storage(tmp_path):
    return LocalVideoStorage(tmp_path / "videos")


@pytest.mark.parametrize(
    "bad", ["../x.mp4", "/etc/passwd", "a/../../x", "C:/x.mp4", "a\\b.mp4", ""]
)
def test_storage_blocks_escape(storage, bad):
    with pytest.raises(StoragePathError):
        storage.resolve(bad)


def test_storage_blocks_symlink_escape(storage, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.mp4").write_bytes(b"x")
    storage.root.mkdir(parents=True)
    (storage.root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(StoragePathError):
        storage.resolve("link/secret.mp4")
    assert storage.open_path("link/secret.mp4") is None


def test_storage_commit_and_delete(storage):
    tmp = storage.temp_file(".mp4")
    tmp.write_bytes(b"data")
    target = storage.commit(tmp, "2026/10/a.mp4")
    assert target.read_bytes() == b"data" and not tmp.exists()
    assert storage.open_path("2026/10/a.mp4") == target
    assert storage.delete("2026/10/a.mp4") is True
    assert storage.delete("2026/10/a.mp4") is False
    assert storage.is_writable()


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("bytes=0-", (0, 999)),
        ("bytes=100-199", (100, 199)),
        ("bytes=900-5000", (900, 999)),
        ("bytes=-100", (900, 999)),
        ("bytes=-5000", (0, 999)),
        ("bytes=0-1,5-9", None),
        ("items=0-1", None),
        ("bytes=abc", None),
        ("bytes=10-5", None),
    ],
)
def test_parse_range(header, expected):
    assert parse_range(header, 1000) == expected


@pytest.mark.parametrize("header", ["bytes=1000-", "bytes=5000-6000", "bytes=-0"])
def test_parse_range_not_satisfiable(header):
    with pytest.raises(RangeNotSatisfiable):
        parse_range(header, 1000)


def test_iter_file(tmp_path):
    path = tmp_path / "f.bin"
    path.write_bytes(bytes(range(256)) * 4)
    assert b"".join(iter_file(path, 10, 19, chunk=3)) == bytes(range(10, 20))
