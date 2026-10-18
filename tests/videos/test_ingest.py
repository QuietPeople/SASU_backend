"""영상 업로드 파이프라인을 ffmpeg로 만든 실제 샘플 영상으로 검증한다. DB를 쓰지 않는다."""

import io
import shutil
import subprocess
from pathlib import Path

import pytest

from app.integrations.ffmpeg import probe
from app.integrations.storage import LocalVideoStorage
from app.modules.videos.errors import (
    DurationOutOfRange,
    EmptyFile,
    FileTooLarge,
    ProbeFailed,
    UnsupportedMedia,
)
from app.modules.videos.policy import VideoPolicy
from app.modules.videos.service import VideoIngestService, sanitize_original_name

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg/ffprobe 필요"
)

FFMPEG = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]


def make_video(path, *, seconds=3, vcodec="libx264", acodec="aac", size="320x568", extra=()):
    cmd = [*FFMPEG, "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=24:duration={seconds}"]
    if acodec:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    cmd += ["-c:v", vcodec, "-pix_fmt", "yuv420p"]
    if vcodec == "libx265":
        cmd += ["-x265-params", "log-level=error"]
    cmd += ["-c:a", acodec] if acodec else ["-an"]
    cmd += [*extra, str(path)]
    subprocess.run(cmd, check=True)
    return path


def moov_before_mdat(path: Path) -> bool:
    data = path.read_bytes()
    return 0 <= data.find(b"moov") < data.find(b"mdat")


@pytest.fixture(scope="module")
def samples(tmp_path_factory):
    d = tmp_path_factory.mktemp("samples")
    s = {
        "mp4": make_video(d / "basic.mp4"),
        "mov_pcm": make_video(d / "phone.mov", acodec="pcm_s16le"),
        "silent": make_video(d / "silent.mp4", acodec=None),
        "webm": make_video(
            d / "clip.webm",
            vcodec="libvpx-vp9",
            acodec="libopus",
            extra=("-b:v", "200k", "-deadline", "realtime", "-cpu-used", "8"),
        ),
        "mkv": make_video(d / "clip.mkv"),
        "hevc": make_video(d / "hevc.mp4", vcodec="libx265", acodec=None, extra=("-tag:v", "hvc1")),
        "long": make_video(d / "long.mp4", seconds=8, acodec=None),
    }
    land = make_video(d / "land.mp4", size="568x320")
    rotated = d / "rotated.mp4"
    try:  # ffmpeg 6 이상
        subprocess.run(
            [*FFMPEG, "-display_rotation", "90", "-i", str(land), "-c", "copy", str(rotated)],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:  # ffmpeg 4·5
        subprocess.run(
            [*FFMPEG, "-i", str(land), "-c", "copy", "-metadata:s:v:0", "rotate=90", str(rotated)],
            check=True,
        )
    s["rotated"] = rotated
    (d / "fake.mp4").write_text("#EXTM3U\nhttp://example.invalid/x.ts\n")
    s["fake"] = d / "fake.mp4"
    data = s["mp4"].read_bytes()
    (d / "truncated.mp4").write_bytes(data[: len(data) // 3])
    s["truncated"] = d / "truncated.mp4"
    return s


@pytest.fixture
def storage(tmp_path):
    return LocalVideoStorage(tmp_path / "videos")


@pytest.fixture
def service(storage):
    return VideoIngestService(storage, VideoPolicy(max_duration_sec=6, max_bytes=20 * 1024 * 1024))


def ingest(service, path, name=None):
    with open(path, "rb") as f:
        return service.ingest(f, name or path.name)


def assert_no_temp_left(storage):
    assert list((storage.root / storage.TMP_DIR).iterdir()) == []


def test_mp4_is_remuxed_with_faststart(service, storage, samples):
    assert not moov_before_mdat(samples["mp4"])
    video = ingest(service, samples["mp4"])
    stored = storage.resolve(video.storage_path)
    assert stored.is_file() and moov_before_mdat(stored)
    assert video.mime_type == "video/mp4"
    assert video.storage_path.count("/") == 2 and video.storage_path.endswith(".mp4")
    assert video.duration_seconds == pytest.approx(3.0, abs=0.15)
    assert video.size_bytes == stored.stat().st_size
    assert (video.probe.video_codec, video.probe.audio_codec) == ("h264", "aac")
    assert_no_temp_left(storage)


def test_pcm_audio_is_converted_to_aac(service, samples):
    video = ingest(service, samples["mov_pcm"])
    assert video.mime_type == "video/mp4" and video.probe.audio_codec == "aac"
    assert video.notes


def test_silent_video_is_accepted(service, samples):
    assert ingest(service, samples["silent"]).probe.audio_codec is None


def test_webm_is_kept_as_webm(service, samples):
    video = ingest(service, samples["webm"])
    assert video.mime_type == "video/webm" and video.storage_path.endswith(".webm")


def test_mkv_h264_becomes_mp4(service, samples):
    assert ingest(service, samples["mkv"]).mime_type == "video/mp4"


def test_rotation_is_kept(service, samples):
    video = ingest(service, samples["rotated"])
    assert video.probe.rotation in (90, 270) and video.probe.is_vertical
    assert (video.summary()["width"], video.summary()["height"]) == (320, 568)


def test_discard_removes_file(service, storage, samples):
    video = ingest(service, samples["mp4"])
    path = storage.resolve(video.storage_path)
    video.discard()
    video.discard()
    assert not path.exists()


def test_original_name_is_sanitized(service, samples):
    video = ingest(service, samples["mp4"], name="..\\..\\C:/temp/회의\x00 영상.mp4")
    assert video.original_name == "회의 영상.mp4"
    assert "회의" not in video.storage_path


@pytest.mark.parametrize(
    ("key", "error"),
    [
        ("hevc", UnsupportedMedia),
        ("long", DurationOutOfRange),
        ("fake", UnsupportedMedia),
        ("truncated", (ProbeFailed, UnsupportedMedia)),
    ],
)
def test_rejections_leave_no_files(service, storage, samples, key, error):
    with pytest.raises(error) as caught:
        ingest(service, samples[key])
    assert caught.value.fields == ["video"]
    assert_no_temp_left(storage)
    assert not any(p.is_file() for p in storage.root.rglob("*") if storage.TMP_DIR not in p.parts)


def test_hevc_message_guides_to_h264(service, samples):
    with pytest.raises(UnsupportedMedia, match="H.264"):
        ingest(service, samples["hevc"])


def test_empty_file(service, storage):
    with pytest.raises(EmptyFile):
        service.ingest(io.BytesIO(b""), "a.mp4")
    assert_no_temp_left(storage)


def test_too_large_stops_while_streaming(storage, samples):
    small = VideoIngestService(storage, VideoPolicy(max_bytes=10_000))
    with open(samples["mp4"], "rb") as f, pytest.raises(FileTooLarge) as caught:
        small.ingest(f, "a.mp4")
    assert caught.value.status_code == 413
    assert_no_temp_left(storage)


def test_probe_reads_size_and_rate(samples):
    info = probe(samples["mp4"])
    assert (info.width, info.height) == (320, 568)
    assert info.frame_rate == pytest.approx(24.0, abs=0.01)


def test_sanitize_original_name():
    assert sanitize_original_name(None) == "video"
    assert sanitize_original_name("a/b/c.mp4") == "c.mp4"
    assert len(sanitize_original_name("가" * 400 + ".mp4")) == 255
