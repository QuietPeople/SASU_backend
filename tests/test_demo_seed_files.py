# 임시 seed 영상 복사·실패 정리 검증. demo_seeds/ 제거 시 함께 제거한다.
import hashlib
import json
import unicodedata
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

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
    records = []
    for number in (1, 2):
        data = f"file-{number}".encode()
        name = f"엑셀 기초 {number}.mp4"
        (directory / "videos" / name).write_bytes(data)
        records.append(
            {
                "storage_path": f"demo/{number}.mp4",
                "video_asset_id": f"00000000-0000-0000-0000-{number:012}",
                "original_name": name,
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    sql = "$sasu_demo_data$" + json.dumps({"contents": records}) + "$sasu_demo_data$"
    (directory / "seed.sql").write_text(sql)
    return directory


class FakeEngine:
    def __init__(self, *, sql_error=None, commit_error=None, stored_videos=()):
        self.connection = Mock()
        self.connection.scalar.return_value = 0
        self.connection.execute.return_value.mappings.return_value = stored_videos
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
        seed_module.apply_demo_seed(engine, bundle, tmp_path / "server")
    engine.connection.exec_driver_sql.assert_not_called()


@pytest.mark.parametrize("failure", ["sql", "commit"])
def test_failure_removes_only_new_copies(seed_module, bundle, tmp_path, failure):
    server = tmp_path / "server"
    (server / "demo").mkdir(parents=True)
    (server / "demo/1.mp4").write_bytes(b"file-1")
    engine = FakeEngine(**{f"{failure}_error": RuntimeError("failed")})
    with pytest.raises(RuntimeError, match="failed"):
        seed_module.apply_demo_seed(engine, bundle, server)
    assert (server / "demo/1.mp4").read_bytes() == b"file-1"
    assert not (server / "demo/2.mp4").exists()
    assert (bundle / "videos/엑셀 기초 2.mp4").read_bytes() == b"file-2"


def test_existing_different_video_is_not_overwritten(seed_module, bundle, tmp_path):
    server = tmp_path / "server"
    (server / "demo").mkdir(parents=True)
    (server / "demo/2.mp4").write_bytes(b"other-existing-file")
    engine = FakeEngine()
    with pytest.raises(RuntimeError, match="기존 서버 영상과 충돌"):
        seed_module.apply_demo_seed(engine, bundle, server)
    assert not (server / "demo/1.mp4").exists()
    assert (server / "demo/2.mp4").read_bytes() == b"other-existing-file"
    engine.connection.exec_driver_sql.assert_not_called()


def test_repeat_reuses_identical_server_copies(seed_module, bundle, tmp_path):
    server = tmp_path / "server"
    engine = FakeEngine()
    assert seed_module.apply_demo_seed(engine, bundle, server) == 2
    assert seed_module.apply_demo_seed(engine, bundle, server) == 0
    assert (server / "demo/1.mp4").read_bytes() == b"file-1"
    assert (server / "demo/2.mp4").read_bytes() == b"file-2"


def test_korean_original_names_work_with_decomposed_filesystem_names(seed_module, bundle, tmp_path):
    original = bundle / "videos/엑셀 기초 1.mp4"
    original.rename(original.with_name(unicodedata.normalize("NFD", original.name)))
    assert seed_module.apply_demo_seed(FakeEngine(), bundle, tmp_path / "server") == 2


def test_already_applied_seed_does_not_require_bundle_or_replace_server_files(
    seed_module, bundle, tmp_path
):
    for path in (bundle / "videos").glob("*.mp4"):
        path.unlink()
    server = tmp_path / "server"
    server.mkdir()
    replacement = server / "replacement.mp4"
    replacement.write_bytes(b"edited video")
    engine = FakeEngine(stored_videos=[
        {"content_id": 12, "storage_path": "replacement.mp4", "size_bytes": 12},
    ])
    engine.connection.scalar.return_value = 2
    assert seed_module.apply_demo_seed(engine, bundle, server) == 0
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
    engine = FakeEngine(stored_videos=[
        {"content_id": 12, "storage_path": relative, "size_bytes": 12},
    ])
    engine.connection.scalar.return_value = 2
    with pytest.raises(RuntimeError, match="서버 영상 확인 실패.*") as error:
        seed_module.apply_demo_seed(engine, bundle, server)
    assert f"콘텐츠 12 / {relative}" in str(error.value)
    if state == "wrong_size":
        assert (server / relative).read_bytes() == b"short"
    assert not (server / "demo").exists()


def test_missing_server_video_exits_without_success_message(
    seed_module, bundle, tmp_path, monkeypatch, capsys
):
    engine = FakeEngine(stored_videos=[
        {"content_id": 12, "storage_path": "missing.mp4", "size_bytes": 12},
    ])
    engine.connection.scalar.return_value = 2
    monkeypatch.setattr(seed_module, "BUNDLE_ROOT", bundle)
    monkeypatch.setattr(seed_module, "get_engine", lambda: engine)
    monkeypatch.setattr(
        seed_module, "get_settings", lambda: Mock(video_storage_root=tmp_path / "server")
    )
    close = Mock()
    monkeypatch.setattr(seed_module, "close_database", close)
    with pytest.raises(SystemExit, match="데모 seed 처리 중단") as error:
        seed_module.main()
    assert "missing.mp4" in str(error.value)
    assert "데모 seed 처리 완료" not in capsys.readouterr().out
    close.assert_called_once()
