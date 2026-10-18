import shutil
import subprocess

import pytest


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
