import json
import shutil
import subprocess
import tempfile
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, BinaryIO, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.integrations.storage import EmptyUploadError

# ffprobe의 MOV/MP4 demuxer 이름만으로는 QuickTime·3GP와 MP4를 구분할 수 없다.
MP4_BRANDS = frozenset(
    {"isom", "mp41", "mp42", "avc1", "dash", "M4V", "M4VH", "M4VP", "MSNV"}
    | {f"iso{number}" for number in range(2, 10)}
)


class VideoMetadata(BaseModel):
    """클라이언트 입력이 아닌 서버 검증·측정 결과."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    mime_type: Annotated[str, Field(min_length=1, max_length=100)]
    duration_seconds: Annotated[
        Decimal, Field(gt=0, allow_inf_nan=False, max_digits=12, decimal_places=3)
    ]


class VideoProcessingUnavailableError(Exception):
    pass


class UnsupportedVideoError(Exception):
    pass


class InvalidVideoError(Exception):
    pass


class VideoInspectionTimeoutError(Exception):
    pass


class VideoInspector(Protocol):
    def inspect(self, stream: BinaryIO) -> VideoMetadata:
        """실제 파일을 검증하고 DB에 저장할 MIME·길이를 반환한다."""
        ...


class FFprobeVideoInspector:
    def __init__(self, executable: str = "ffprobe", timeout_seconds: float = 30):
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def inspect(self, stream: BinaryIO) -> VideoMetadata:
        # moov가 파일 끝에 있는 MP4도 탐색할 수 있도록 seek 가능한 로컬 파일을 사용한다.
        # 원본 이름·클라이언트 MIME은 검사에 사용하지 않는다.
        with tempfile.TemporaryDirectory(prefix="sasu-video-") as directory:
            source = Path(directory) / "input.upload"
            with source.open("xb") as output:
                stream.seek(0)
                shutil.copyfileobj(stream, output, length=1024 * 1024)
                if output.tell() == 0:
                    raise EmptyUploadError
            try:
                result = subprocess.run(
                    [
                        self.executable,
                        "-v",
                        "error",
                        "-protocol_whitelist",
                        "file",
                        "-format_whitelist",
                        "mov",
                        "-show_entries",
                        "format=format_name,duration:format_tags=major_brand:"
                        "stream=codec_type,width,height,duration:stream_disposition=attached_pic",
                        "-of",
                        "json",
                        str(source),
                    ],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise VideoProcessingUnavailableError from exc
            except subprocess.TimeoutExpired as exc:
                raise VideoInspectionTimeoutError from exc
            if result.returncode != 0:
                raise InvalidVideoError
            return self._metadata(result.stdout)

    @staticmethod
    def _metadata(output: bytes) -> VideoMetadata:
        try:
            data = json.loads(output)
            container = data["format"]
            brand = container.get("tags", {}).get("major_brand", "").strip()
            if "mp4" not in container["format_name"].split(",") or brand not in MP4_BRANDS:
                raise UnsupportedVideoError
            videos = [
                stream
                for stream in data["streams"]
                if stream.get("codec_type") == "video"
                and not stream.get("disposition", {}).get("attached_pic", 0)
                and stream.get("width", 0) > 0
                and stream.get("height", 0) > 0
            ]
            if not videos:
                raise InvalidVideoError
            raw_duration = videos[0].get("duration")
            if raw_duration in (None, "N/A"):
                raw_duration = container["duration"]
            duration = Decimal(raw_duration)
            if not duration.is_finite() or duration <= 0:
                raise InvalidVideoError
            # DB NUMERIC(12, 3)에 맞추되, 0으로 반올림되는 길이는 허용하지 않는다.
            duration = duration.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            return VideoMetadata(mime_type="video/mp4", duration_seconds=duration)
        except (ValueError, TypeError, KeyError, AttributeError, InvalidOperation) as exc:
            raise InvalidVideoError from exc


def get_video_inspector() -> VideoInspector:
    return FFprobeVideoInspector()
