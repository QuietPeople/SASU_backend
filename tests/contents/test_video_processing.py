import json
import subprocess
from decimal import Decimal
from functools import partial
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.integrations import video_processing
from app.integrations.storage import EmptyUploadError
from app.integrations.video_processing import (
    FFprobeVideoInspector,
    InvalidVideoError,
    UnsupportedVideoError,
    VideoInspectionTimeoutError,
    VideoProcessingUnavailableError,
)


@pytest.mark.parametrize("sample", ["mp4", "faststart", "fragmented"])
def test_real_mp4_metadata(video_samples, sample):
    with video_samples[sample].open("rb") as stream:
        metadata = FFprobeVideoInspector().inspect(stream)
    assert metadata.mime_type == "video/mp4"
    assert metadata.duration_seconds == Decimal("1.200")


def probe_result(*, duration="1.2345", brand="isom", streams=None):
    if streams is None:
        streams = [{"codec_type": "video", "width": 32, "height": 32}]
    return {
        "format": {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": duration,
            "tags": {"major_brand": brand},
        },
        "streams": streams,
    }


@pytest.mark.parametrize(
    "data,error",
    [
        (probe_result(duration="NaN"), InvalidVideoError),
        (probe_result(duration="Infinity"), InvalidVideoError),
        (probe_result(duration="-1"), InvalidVideoError),
        (probe_result(duration="0"), InvalidVideoError),
        (probe_result(duration="0.0001"), InvalidVideoError),
        (probe_result(duration="1000000000"), InvalidVideoError),
        (probe_result(duration="N/A"), InvalidVideoError),
        (probe_result(streams=[]), InvalidVideoError),
        (probe_result(streams=[{"codec_type": "audio"}]), InvalidVideoError),
        (
            probe_result(
                streams=[
                    {
                        "codec_type": "video",
                        "width": 32,
                        "height": 32,
                        "disposition": {"attached_pic": 1},
                    }
                ]
            ),
            InvalidVideoError,
        ),
        (
            probe_result(streams=[{"codec_type": "video", "width": 0, "height": 32}]),
            InvalidVideoError,
        ),
        (probe_result(brand="qt  "), UnsupportedVideoError),
        (probe_result(brand="3gp4"), UnsupportedVideoError),
        ({}, InvalidVideoError),
        ([], InvalidVideoError),
    ],
)
def test_invalid_metadata_cleans_temporary_files(monkeypatch, tmp_path, data, error):
    monkeypatch.setattr(
        video_processing.tempfile, "TemporaryDirectory", partial(TemporaryDirectory, dir=tmp_path)
    )

    def run(command, **kwargs):
        assert Path(command[-1]).read_bytes() == b"test-input"
        return subprocess.CompletedProcess(command, 0, json.dumps(data).encode(), b"")

    monkeypatch.setattr(video_processing.subprocess, "run", run)
    with pytest.raises(error):
        FFprobeVideoInspector().inspect(BytesIO(b"test-input"))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("failure", ["timeout", "missing", "invalid_json", "exit", "empty", "io"])
def test_inspection_failures_clean_temporary_files(monkeypatch, tmp_path, failure):
    monkeypatch.setattr(
        video_processing.tempfile, "TemporaryDirectory", partial(TemporaryDirectory, dir=tmp_path)
    )

    def run(command, **kwargs):
        assert kwargs["timeout"] == 30
        assert kwargs["stdin"] == subprocess.DEVNULL
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 30)
        if failure == "missing":
            raise FileNotFoundError
        return subprocess.CompletedProcess(
            command, 1 if failure == "exit" else 0, b"not-json", b"private diagnostic"
        )

    class BrokenStream(BytesIO):
        def read(self, size=-1):
            raise OSError("stream interrupted")

    monkeypatch.setattr(video_processing.subprocess, "run", run)
    error = {
        "timeout": VideoInspectionTimeoutError,
        "missing": VideoProcessingUnavailableError,
        "invalid_json": InvalidVideoError,
        "exit": InvalidVideoError,
        "empty": EmptyUploadError,
        "io": OSError,
    }[failure]
    stream = (
        BrokenStream(b"input")
        if failure == "io"
        else BytesIO(b"" if failure == "empty" else b"input")
    )
    with pytest.raises(error):
        FFprobeVideoInspector().inspect(stream)
    assert list(tmp_path.iterdir()) == []


def test_duration_rounding_and_stream_duration_precedence(monkeypatch):
    data = probe_result(
        duration="100",
        streams=[
            {
                "codec_type": "video",
                "width": 32,
                "height": 32,
                "duration": "1.2345",
            }
        ],
    )
    monkeypatch.setattr(
        video_processing.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, json.dumps(data).encode()
        ),
    )
    metadata = FFprobeVideoInspector().inspect(BytesIO(b"input"))
    assert metadata.duration_seconds == Decimal("1.235")
