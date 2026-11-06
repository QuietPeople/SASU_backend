import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.integrations import ffmpeg
from app.integrations.ffmpeg import ProbeResult
from app.modules.videos.errors import DurationOutOfRange, ProcessingFailed
from app.modules.videos.policy import VideoPolicy
from app.modules.videos.service import NormalizePlan, OutputKind, _verify_normalized


def test_probe_excludes_cover_and_preserves_absolute_stream_indices(monkeypatch, tmp_path):
    payload = {
        "format": {"duration": "3"},
        "streams": [
            {"index": 0, "codec_type": "video", "disposition": {"attached_pic": 1}},
            {"index": 1, "codec_type": "subtitle"},
            {"index": 2, "codec_type": "audio", "codec_name": "aac"},
            {"index": 3, "codec_type": "video", "codec_name": "h264", "width": 320, "height": 568},
        ],
    }
    monkeypatch.setattr(ffmpeg, "_binary", lambda name: name)
    monkeypatch.setattr(
        ffmpeg.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(payload)),
    )
    result = ffmpeg.probe(tmp_path / "sample.mp4")
    assert (result.video_stream_index, result.audio_stream_index) == (3, 2)
    assert (result.video_codec, result.width, result.height) == ("h264", 320, 568)


@pytest.mark.parametrize("scaled", [False, True])
@pytest.mark.parametrize("audio_index", [None, 2])
def test_both_conversion_paths_map_only_inspected_streams(
    monkeypatch, tmp_path, scaled, audio_index
):
    result = ProbeResult(3, "h264", 320, 568, 0, "aac" if audio_index else None, 30, 3, audio_index)
    target = tmp_path / "stored.mp4"
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        target.write_bytes(b"converted")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(ffmpeg, "_binary", lambda name: name)
    monkeypatch.setattr(ffmpeg.subprocess, "run", run)
    convert = ffmpeg.scale_and_remux if scaled else ffmpeg.remux
    convert(
        tmp_path / "source.mp4",
        target,
        streams=result,
        output_format="mp4",
        transcode_audio=False,
        timeout=1,
        **({"long_edge": 160} if scaled else {}),
    )
    command = commands[0]
    mappings = [command[i + 1] for i, value in enumerate(command) if value == "-map"]
    assert mappings == (["0:3", "0:2"] if audio_index is not None else ["0:3"])


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"duration_sec": 188}, DurationOutOfRange),
        ({"duration_sec": 0.9}, DurationOutOfRange),
        ({"duration_sec": float("nan")}, DurationOutOfRange),
        ({"duration_sec": float("inf")}, DurationOutOfRange),
        ({"width": 4000, "height": 3000}, ProcessingFailed),
        ({"width": 0}, ProcessingFailed),
        ({"video_codec": "hevc"}, ProcessingFailed),
        ({"audio_codec": "aac"}, ProcessingFailed),
        ({"duration_sec": 160}, ProcessingFailed),
    ],
)
def test_invalid_final_media_is_rejected(changes, error):
    original = ProbeResult(
        180, "h264", 1920, 1080, 0, None, 30, pixel_format="yuv420p", profile="High"
    )
    with pytest.raises(error):
        _verify_normalized(
            original, replace(original, **changes), NormalizePlan(OutputKind.MP4), VideoPolicy()
        )


@pytest.mark.parametrize("seconds", [1, 180])
def test_final_policy_boundaries_are_accepted(seconds):
    result = ProbeResult(
        seconds, "h264", 2160, 1080, 0, None, 30, pixel_format="yuv420p", profile="High"
    )
    _verify_normalized(result, result, NormalizePlan(OutputKind.MP4), VideoPolicy())


@pytest.mark.parametrize(
    "width,height,scale",
    [
        (1920, 1080, None),
        (2160, 1080, None),
        (2560, 1440, 2160),
        (1440, 2560, 2160),
        (3839, 2160, 2160),
        (3840, 2160, 2160),
        (2160, 3840, 2160),
    ],
)
def test_input_limit_is_distinct_from_scale_target(width, height, scale):
    from app.modules.videos.service import decide_plan

    result = ProbeResult(
        3, "h264", width, height, 0, None, 30, pixel_format="yuv420p", profile="High"
    )
    assert decide_plan("isobmff", result, VideoPolicy()).scale_to == scale


@pytest.mark.parametrize("width,height", [(3841, 2160), (2160, 3841), (4096, 2160), (7680, 4320)])
def test_input_above_3840_is_rejected(width, height):
    from app.modules.videos.errors import ResolutionOutOfRange
    from app.modules.videos.service import decide_plan

    result = ProbeResult(
        3, "h264", width, height, 0, None, 30, pixel_format="yuv420p", profile="High"
    )
    with pytest.raises(ResolutionOutOfRange):
        decide_plan("isobmff", result, VideoPolicy())


@pytest.mark.parametrize(
    "codec,pixels,profile",
    [
        ("h264", "yuv444p", "High 4:4:4 Predictive"),
        ("h264", "yuv420p10le", "High 10"),
        ("h264", "yuv420p", None),
        ("vp9", "yuv420p10le", "Profile 2"),
        ("av1", "yuv444p", "High"),
    ],
)
def test_unsupported_pixel_formats_and_profiles_are_rejected(codec, pixels, profile):
    from app.modules.videos.errors import UnsupportedMedia
    from app.modules.videos.service import decide_plan

    result = ProbeResult(3, codec, 320, 568, 0, None, 30, pixel_format=pixels, profile=profile)
    with pytest.raises(UnsupportedMedia):
        decide_plan("ebml" if codec != "h264" else "isobmff", result, VideoPolicy())


def test_decode_failure_and_timeout_are_input_errors(monkeypatch, tmp_path):
    import subprocess

    from app.modules.videos.errors import ProbeFailed, ProbeTimeout

    info = ProbeResult(3, "h264", 320, 568, 0, None, 30, video_stream_index=3)
    commands = []
    monkeypatch.setattr(ffmpeg, "_binary", lambda name: name)

    def broken(cmd, **kwargs):
        commands.append(cmd)
        assert kwargs["timeout"] == 120
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(ffmpeg.subprocess, "run", broken)
    with pytest.raises(ProbeFailed):
        ffmpeg.validate_decoding(tmp_path / "sample.mp4", info, timeout=120)
    assert commands[0][commands[0].index("-map") + 1] == "0:3"
    assert "-xerror" in commands[0] and "explode" in commands[0]

    def timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 120)

    monkeypatch.setattr(ffmpeg.subprocess, "run", timeout)
    with pytest.raises(ProbeTimeout):
        ffmpeg.validate_decoding(tmp_path / "sample.mp4", info, timeout=120)
