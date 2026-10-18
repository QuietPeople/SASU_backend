import shutil
import subprocess
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.integrations.ffmpeg import ProbeResult
from app.integrations.storage import LocalVideoStorage
from app.modules.videos.errors import EmptyFile
from app.modules.videos.policy import VideoPolicy
from app.modules.videos.service import (
    IngestedVideo,
    VideoIngestService,
    sanitize_original_name,
)


class StubVideoIngest(VideoIngestService):
    """ffmpeg 없이 업로드 바이트를 그대로 저장하는 테스트용 데이터 처리기.

    콘텐츠 API의 권한·revision·DB 연결·실패 정리를 영상 처리와 분리해 검증할 때 쓴다.
    실제 처리 파이프라인은 tests/videos와 video_samples를 쓰는 테스트가 검증한다.
    """

    def __init__(self) -> None:
        super().__init__(LocalVideoStorage(get_settings().video_storage_root), VideoPolicy())

    def ingest(self, src, original_name):
        data = src.read()
        if not data:
            raise EmptyFile("빈 파일입니다.")
        asset_id = uuid4()
        temp = self.storage.temp_file(".mp4")
        temp.write_bytes(data)
        relative_path = self.storage.new_relative_path(asset_id, ".mp4")
        stored = self.storage.commit(temp, relative_path)
        return IngestedVideo(
            asset_id=asset_id,
            storage_path=relative_path,
            original_name=sanitize_original_name(original_name),
            mime_type="video/mp4",
            size_bytes=stored.stat().st_size,
            duration_seconds=12.345,
            upload_sha256="",
            probe=ProbeResult(12.345, "h264", 32, 32, 0, None, None),
            _storage=self.storage,
        )


def _stored_files() -> list:
    root = get_settings().video_storage_root
    return sorted(root.iterdir()) if root.exists() else []


@pytest.fixture
def stub_video_ingest():
    """dependency_overrides[get_video_ingest_service]에 넣을 테스트용 처리기 클래스."""
    return StubVideoIngest


@pytest.fixture
def stored_files():
    """저장 루트에 남은 파일 목록을 돌려주는 함수. 루트가 아직 없으면 빈 목록."""
    return _stored_files


@pytest.fixture(scope="session")
def video_samples(tmp_path_factory):
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None or shutil.which("ffprobe") is None:
        pytest.skip("실제 영상 검증에는 ffmpeg·ffprobe가 필요합니다. Docker 이미지에 포함됩니다.")
    root = tmp_path_factory.mktemp("video-samples")

    def generate(name, *arguments):
        path = root / name
        subprocess.run(
            [ffmpeg, "-v", "error", "-nostdin", *arguments, str(path)],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return path

    video_input = ["-f", "lavfi", "-i", "color=c=blue:s=32x32:r=10", "-t", "1.2"]
    video_codec = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-threads", "1"]
    normal = generate("normal.mp4", *video_input, *video_codec)
    samples = {
        "mp4": normal,
        "faststart": generate(
            "faststart.mp4", *video_input, *video_codec, "-movflags", "+faststart"
        ),
        "fragmented": generate(
            "fragmented.mp4", *video_input, *video_codec, "-movflags", "+frag_keyframe+empty_moov"
        ),
        "mov": generate("quicktime.mov", *video_input, *video_codec),
        "matroska": generate("video.mkv", *video_input, *video_codec),
        "audio": generate(
            "audio.mp4", "-f", "lavfi", "-i", "sine=frequency=440", "-t", "1.2", "-c:a", "aac"
        ),
    }
    for key, data in {
        "fake": b"This is not an MP4 video.",
        "empty": b"",
        "truncated": normal.read_bytes()[:64],
    }.items():
        samples[key] = root / f"{key}.mp4"
        samples[key].write_bytes(data)
    return samples
